from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.database import RunRow
from aggregator_demo.input_registry import DemoInputRegistry
from aggregator_demo.modbus_tcp import ModbusTcpClient
from aggregator_demo.ot_gateway import DispatchGateway
from aggregator_demo.plc_simulator import SimulatedPLCServer, SimulatedSiteController
from aggregator_demo.run_repository import RunRepository


DEMO_INPUT = DemoInputRegistry().descriptor("demo/depot-a-8-v1")
CONTROL_HEADERS = {
    "X-Control-Key": "dispatch-test-key",
    "X-Operator-ID": "ot-supervisor@example.test",
}


def _build_candidate(
    tmp_path: Path,
    gateway: DispatchGateway,
    *,
    decision: str = "approved",
    buy: list[float] | None = None,
):
    app = create_app(
        database_url=f"sqlite:///{(tmp_path / f'{uuid4()}.db').as_posix()}",
        initialize_schema=True,
        control_api_key="dispatch-test-key",
        emergency_api_key="emergency-test-key",
        control_gateway=gateway,
    )
    client = TestClient(app)
    created = client.post(
        "/api/v1/runs",
        json={
            "run_type": "day_ahead",
            "optimization_mode": "selfish",
            "input_reference": DEMO_INPUT.reference,
            "input_sha256": DEMO_INPUT.sha256,
            "v2g_enabled": True,
            "agent_backend": "rule",
            "scenario_ids": ["ot-integration"],
        },
    ).json()
    run_id = UUID(created["id"])
    with app.state.session_factory() as session:
        repository = RunRepository(session)
        repository.claim_next(worker_id="ot-integration-worker")
        repository.complete(
            run_id,
            {
                "solver_name": "security-test",
                "w_buy": buy or [40.0, 20.0],
                "w_sell": [0.0] * len(buy) if buy is not None else [10.0, 0.0],
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


def test_approved_dispatch_crosses_real_tcp_and_persists_correlated_evidence(tmp_path: Path):
    controller = SimulatedSiteController(site_capacity_kw=10_000.0)
    with SimulatedPLCServer(controller=controller) as plc:
        gateway = DispatchGateway(ModbusTcpClient(*plc.address, retries=0))
        app, client, run_id = _build_candidate(tmp_path, gateway)
        url = f"/api/v1/runs/{run_id}/dispatch-simulations"

        dispatched = client.post(url, json={"interval_index": 1}, headers=CONTROL_HEADERS)

        assert dispatched.status_code == 201
        body = dispatched.json()
        assert body["decision"] == "accepted"
        assert body["setpoint_kw"] == 60.0
        assert body["modbus_frame_hex"]
        assert body["response_frame_hex"]
        assert body["controller_response"]["measured_site_power_kw"] == 60.0
        assert all(check["passed"] for check in body["policy_checks"])
        assert client.get(url, headers=CONTROL_HEADERS).json()["items"][0] == body
        event = client.get("/api/v1/security/events").json()["items"][0]
        assert event["correlation_id"] == body["correlation_id"]
        assert event["reason_code"] == "dispatch_applied"
        assert client.get(f"/api/v1/runs/{run_id}/timeline").json()["events"][-1][
            "event_type"
        ] == "dispatch_accepted"
        app.state.database_engine.dispose()


def test_invalid_credential_and_hash_mismatch_are_both_persisted(tmp_path: Path):
    with SimulatedPLCServer() as plc:
        gateway = DispatchGateway(ModbusTcpClient(*plc.address, retries=0))
        app, client, run_id = _build_candidate(tmp_path, gateway)
        url = f"/api/v1/runs/{run_id}/dispatch-simulations"

        invalid = client.post(
            url,
            json={"interval_index": 1},
            headers={"X-Control-Key": "wrong", "X-Operator-ID": "intruder@example.test"},
        )
        assert invalid.status_code == 401
        assert invalid.json()["reason_code"] == "invalid_credential"

        with app.state.session_factory() as session:
            run = session.get(RunRow, str(run_id))
            run.result_sha256 = "0" * 64
            session.commit()
        mismatch = client.post(url, json={"interval_index": 1}, headers=CONTROL_HEADERS)
        assert mismatch.status_code == 409
        assert mismatch.json()["reason_code"] == "approval_result_hash"

        attempts = client.get(url, headers=CONTROL_HEADERS).json()["items"]
        assert [item["decision"] for item in attempts] == ["rejected", "rejected"]
        assert {item["reason_code"] for item in attempts} == {
            "invalid_credential",
            "approval_result_hash",
        }
        app.state.database_engine.dispose()


def test_rejected_candidate_never_reaches_the_gateway(tmp_path: Path):
    controller = SimulatedSiteController()
    with SimulatedPLCServer(controller=controller) as plc:
        gateway = DispatchGateway(ModbusTcpClient(*plc.address, retries=0))
        app, client, run_id = _build_candidate(tmp_path, gateway, decision="rejected")

        response = client.post(
            f"/api/v1/runs/{run_id}/dispatch-simulations",
            json={"interval_index": 1},
            headers=CONTROL_HEADERS,
        )

        assert response.status_code == 409
        assert response.json()["reason_code"] == "immutable_operator_approval"
        assert response.json()["modbus_frame_hex"] is None
        assert controller.registers[100] == 0
        assert controller.registers[101] == 0
        app.state.database_engine.dispose()


def test_replay_and_stale_commands_are_rejected_and_correlated(tmp_path: Path):
    with SimulatedPLCServer() as plc:
        gateway = DispatchGateway(ModbusTcpClient(*plc.address, retries=0))
        app, client, run_id = _build_candidate(tmp_path, gateway)
        url = f"/api/v1/runs/{run_id}/dispatch-simulations"
        command_id = str(uuid4())

        accepted = client.post(
            url,
            json={"interval_index": 1, "command_id": command_id},
            headers=CONTROL_HEADERS,
        )
        replay = client.post(
            url,
            json={"interval_index": 1, "command_id": command_id},
            headers=CONTROL_HEADERS,
        )
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        stale = client.post(
            url,
            json={
                "interval_index": 1,
                "issued_at": stale_time.isoformat(),
                "expires_at": (stale_time + timedelta(seconds=20)).isoformat(),
            },
            headers=CONTROL_HEADERS,
        )

        assert accepted.status_code == 201
        assert replay.status_code == 409
        assert replay.json()["reason_code"] == "replayed_command"
        assert stale.status_code == 409
        assert stale.json()["reason_code"] == "stale_command"
        events = client.get("/api/v1/security/events").json()["items"]
        assert {event["reason_code"] for event in events} >= {
            "dispatch_applied",
            "replayed_command",
            "stale_command",
        }
        app.state.database_engine.dispose()


def test_out_of_range_schedule_is_blocked_before_controller(tmp_path: Path):
    with SimulatedPLCServer() as plc:
        gateway = DispatchGateway(ModbusTcpClient(*plc.address, retries=0))
        app, client, run_id = _build_candidate(tmp_path, gateway, buy=[900.0])

        response = client.post(
            f"/api/v1/runs/{run_id}/dispatch-simulations",
            json={"interval_index": 1},
            headers=CONTROL_HEADERS,
        )

        assert response.status_code == 409
        assert response.json()["reason_code"] == "site_capacity_envelope"
        assert response.json()["modbus_frame_hex"] is None
        app.state.database_engine.dispose()


def test_emergency_path_uses_separate_key_and_sets_safe_state(tmp_path: Path):
    controller = SimulatedSiteController()
    with SimulatedPLCServer(controller=controller) as plc:
        gateway = DispatchGateway(ModbusTcpClient(*plc.address, retries=0))
        app, client, _ = _build_candidate(tmp_path, gateway)

        denied = client.post(
            "/api/v1/emergency-safe-state",
            json={"reason": "heartbeat loss drill"},
            headers={"X-Emergency-Key": "wrong"},
        )
        accepted = client.post(
            "/api/v1/emergency-safe-state",
            json={"reason": "heartbeat loss drill"},
            headers={
                "X-Emergency-Key": "emergency-test-key",
                "X-Operator-ID": "incident-commander@example.test",
            },
        )

        assert denied.status_code == 401
        assert accepted.status_code == 201
        assert accepted.json()["action"] == "safe_state"
        assert accepted.json()["controller_response"]["controller_state"] == "safe_state"
        assert client.get("/api/v1/security/events").json()["items"][0][
            "event_type"
        ] == "emergency_safe_state_activated"
        app.state.database_engine.dispose()
