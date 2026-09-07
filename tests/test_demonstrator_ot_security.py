from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.database import RunRow
from aggregator_demo.input_registry import DemoInputRegistry
from aggregator_demo.ot_security import decode_site_power_write, encode_site_power_write
from aggregator_demo.run_repository import RunRepository


DEMO_INPUT = DemoInputRegistry().descriptor("demo/depot-a-8-v1")
CONTROL_HEADERS = {
    "X-Control-Key": "test-control-key",
    "X-Operator-ID": "ot-supervisor@example.test",
}


def request_body():
    return {
        "run_type": "day_ahead",
        "optimization_mode": "selfish",
        "input_reference": DEMO_INPUT.reference,
        "input_sha256": DEMO_INPUT.sha256,
        "v2g_enabled": True,
        "agent_backend": "rule",
        "scenario_ids": ["nominal"],
    }


def build_candidate(tmp_path: Path, *, decision: str = "approved", buy=None, sell=None):
    database_url = f"sqlite:///{(tmp_path / 'ot-security.db').as_posix()}"
    app = create_app(
        database_url=database_url,
        initialize_schema=True,
        control_api_key="test-control-key",
    )
    client = TestClient(app)
    created = client.post("/api/v1/runs", json=request_body()).json()
    run_id = UUID(created["id"])
    with app.state.session_factory() as session:
        repository = RunRepository(session)
        assert repository.claim_next(worker_id="ot-security-test-worker") is not None
        repository.complete(
            run_id,
            {
                "solver_name": "security-test",
                "w_buy": buy if buy is not None else [40.0, 20.0],
                "w_sell": sell if sell is not None else [10.0, 0.0],
                "validation": {"passed": True},
            },
        )
    approval = client.post(
        f"/api/v1/runs/{run_id}/approval",
        json={"decision": decision},
        headers={"X-Operator-ID": "planner@example.test"},
    )
    assert approval.status_code == 201
    return app, client, run_id


def test_control_simulation_requires_separate_credential(tmp_path: Path):
    app, client, run_id = build_candidate(tmp_path)

    missing = client.post(
        f"/api/v1/runs/{run_id}/control-simulations",
        json={"interval_index": 1},
    )
    wrong = client.post(
        f"/api/v1/runs/{run_id}/control-simulations",
        json={"interval_index": 1},
        headers={"X-Control-Key": "wrong"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "control_authentication_failed"
    app.state.database_engine.dispose()


def test_modbus_register_round_trip_preserves_v2g_export_sign():
    frame = encode_site_power_write(-42.3, transaction_id=9)

    decoded = decode_site_power_write(frame)
    assert decoded["transaction_id"] == 9
    assert decoded["unit_id"] == 1
    assert decoded["register_address"] == 100
    assert decoded["setpoint_kw"] == pytest.approx(-42.3)


def test_control_simulation_fails_closed_when_not_configured(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'disabled.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    response = TestClient(app).post(
        "/api/v1/runs/00000000-0000-0000-0000-000000000001/control-simulations",
        json={"interval_index": 1},
        headers={"X-Control-Key": "unused"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "control_simulation_disabled"
    app.state.database_engine.dispose()


def test_approved_interval_is_encoded_and_recorded_idempotently(tmp_path: Path):
    app, client, run_id = build_candidate(tmp_path)
    url = f"/api/v1/runs/{run_id}/control-simulations"

    first = client.post(url, json={"interval_index": 1}, headers=CONTROL_HEADERS)
    repeated = client.post(url, json={"interval_index": 1}, headers=CONTROL_HEADERS)

    assert first.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json() == first.json()
    body = first.json()
    assert body["setpoint_kw"] == 60.0
    assert body["simulated_only"] is True
    assert body["requested_by"] == "ot-supervisor@example.test"
    assert body["policy_version"] == "ot-policy-v1"
    assert [check["code"] for check in body["policy_checks"]] == [
        "immutable_operator_approval",
        "approval_result_hash",
        "deterministic_validation",
        "interval_in_horizon",
        "site_capacity_envelope",
        "signed_register_range",
    ]
    assert all(check["passed"] is True for check in body["policy_checks"])
    decoded = decode_site_power_write(bytes.fromhex(body["modbus_frame_hex"]))
    assert decoded == {
        "transaction_id": 1,
        "unit_id": 1,
        "register_address": 100,
        "setpoint_kw": 60.0,
    }

    listed = client.get(url, headers=CONTROL_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["items"] == [body]
    timeline = client.get(f"/api/v1/runs/{run_id}/timeline")
    assert timeline.json()["events"][-1]["event_type"] == "control_simulated"
    assert "no frame transmitted" in timeline.json()["events"][-1]["detail"]
    app.state.database_engine.dispose()


def test_unapproved_or_rejected_candidate_is_blocked(tmp_path: Path):
    app, client, run_id = build_candidate(tmp_path, decision="rejected")

    response = client.post(
        f"/api/v1/runs/{run_id}/control-simulations",
        json={"interval_index": 1},
        headers=CONTROL_HEADERS,
    )

    assert response.status_code == 409
    assert "requires an immutable operator approval" in response.json()["message"]
    app.state.database_engine.dispose()


def test_interval_capacity_and_result_hash_are_enforced(tmp_path: Path):
    app, client, run_id = build_candidate(tmp_path, buy=[900.0], sell=[0.0])
    url = f"/api/v1/runs/{run_id}/control-simulations"

    unsafe = client.post(url, json={"interval_index": 1}, headers=CONTROL_HEADERS)
    outside = client.post(url, json={"interval_index": 2}, headers=CONTROL_HEADERS)

    assert unsafe.status_code == 409
    assert "exceeds" in unsafe.json()["message"]
    assert unsafe.json()["failed_check"] == "site_capacity_envelope"
    assert outside.status_code == 409
    assert "outside the optimized horizon" in outside.json()["message"]
    assert outside.json()["failed_check"] == "interval_in_horizon"

    with app.state.session_factory() as session:
        row = session.get(RunRow, str(run_id))
        row.result_sha256 = "0" * 64
        session.commit()
    mismatch = client.post(url, json={"interval_index": 1}, headers=CONTROL_HEADERS)
    assert mismatch.status_code == 409
    assert "hash does not match" in mismatch.json()["message"]
    assert mismatch.json()["failed_check"] == "approval_result_hash"
    app.state.database_engine.dispose()
