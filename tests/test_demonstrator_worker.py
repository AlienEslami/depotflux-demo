from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.input_registry import DemoInputRegistry
from aggregator_demo.run_repository import RunRepository
from aggregator_demo.worker import execute_one
from aggregator_demo.optimizer_service import (
    OptimizationInfeasibleError,
    OptimizationTimeoutError,
)


DEMO_INPUT = DemoInputRegistry().descriptor("demo/depot-a-8-v1")


def request_body(**overrides):
    body = {
        "run_type": "day_ahead",
        "optimization_mode": "selfish",
        "input_reference": DEMO_INPUT.reference,
        "input_sha256": DEMO_INPUT.sha256,
        "v2g_enabled": True,
        "agent_backend": "rule",
        "scenario_ids": ["nominal"],
    }
    body.update(overrides)
    return body


def test_worker_executes_real_optimizer_and_persists_validated_result(
    tmp_path: Path,
    monkeypatch,
):
    database_url = f"sqlite:///{(tmp_path / 'worker.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    created = client.post("/api/v1/runs", json=request_body())
    run_id = created.json()["id"]

    pending = client.get(f"/api/v1/runs/{run_id}/result")
    assert pending.status_code == 409
    assert pending.json()["code"] == "run_not_complete"

    monkeypatch.setenv("DA_SOLVER_ORDER", "appsi_highs,highs")
    assert execute_one(database_url=database_url, worker_id="pytest-worker") is True
    assert execute_one(database_url=database_url, worker_id="pytest-worker") is False

    app.state.database_engine.dispose()
    restarted_app = create_app(database_url=database_url, initialize_schema=False)
    restarted_client = TestClient(restarted_app)

    completed = restarted_client.get(f"/api/v1/runs/{run_id}")
    assert completed.status_code == 200
    assert completed.json()["status"] == "succeeded"
    assert completed.json()["started_at"] is not None
    assert completed.json()["completed_at"] is not None

    response = restarted_client.get(f"/api/v1/runs/{run_id}/result")
    assert response.status_code == 200
    body = response.json()
    result = body["result"]
    assert body["status"] == "succeeded"
    assert body["solver_name"] in {"appsi_highs", "highs"}
    assert result["validation"]["passed"] is True
    assert result["optimized_steps"] == 48
    assert len(result["w_buy"]) == 48
    assert len(result["w_sell"]) == 48
    assert len(result["energy"]) == DEMO_INPUT.fleet_size
    canonical = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert body["result_sha256"] == hashlib.sha256(canonical).hexdigest()
    restarted_app.state.database_engine.dispose()


def test_worker_rejects_real_time_run_without_a_preserved_notice(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'unsupported.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    created = client.post(
        "/api/v1/runs",
        json=request_body(run_type="real_time"),
    ).json()

    assert execute_one(database_url=database_url, worker_id="pytest-worker") is True

    result = client.get(f"/api/v1/runs/{created['id']}/result")
    assert result.status_code == 200
    assert result.json()["status"] == "failed"
    assert result.json()["failure_code"] == "notice_not_found"
    assert result.json()["result"] is None
    app.state.database_engine.dispose()


def test_worker_classifies_controlled_infeasible_drill(tmp_path: Path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'infeasible.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    created = client.post(
        "/api/v1/failure-drills",
        json={
            "input_reference": DEMO_INPUT.reference,
            "input_sha256": DEMO_INPUT.sha256,
            "drill_type": "infeasible",
        },
    ).json()

    def assert_isolated(input_data, **_kwargs):
        assert {bus["initial_soc"] for bus in input_data["buses"]} == {0.0}
        raise OptimizationInfeasibleError("controlled model is infeasible")

    monkeypatch.setattr("aggregator_demo.worker.optimize_day_ahead", assert_isolated)
    assert execute_one(database_url=database_url, worker_id="drill-worker") is True

    result = client.get(f"/api/v1/runs/{created['id']}/result").json()
    assert result["status"] == "infeasible"
    assert result["failure_code"] == "optimization_infeasible"
    app.state.database_engine.dispose()


def test_worker_classifies_controlled_timeout_drill(tmp_path: Path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'timeout.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    created = client.post(
        "/api/v1/failure-drills",
        json={
            "input_reference": DEMO_INPUT.reference,
            "input_sha256": DEMO_INPUT.sha256,
            "drill_type": "solver_timeout",
        },
    ).json()

    def assert_tiny_budget(_input_data, **kwargs):
        assert kwargs["solver_time_limit_seconds"] == 0.001
        raise OptimizationTimeoutError("controlled solver timeout")

    monkeypatch.setattr("aggregator_demo.worker.optimize_day_ahead", assert_tiny_budget)
    assert execute_one(database_url=database_url, worker_id="drill-worker") is True

    result = client.get(f"/api/v1/runs/{created['id']}/result").json()
    assert result["status"] == "timed_out"
    assert result["failure_code"] == "solver_time_limit"
    app.state.database_engine.dispose()


def test_worker_requeues_an_abandoned_claim_after_restart(tmp_path: Path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'recovery.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    created = client.post("/api/v1/runs", json=request_body()).json()

    with app.state.session_factory() as session:
        assert RunRepository(session).claim_next(worker_id="interrupted-worker") is not None

    monkeypatch.setattr(
        "aggregator_demo.worker.optimize_day_ahead",
        lambda *_args, **_kwargs: {
            "solver_name": "recovery-test",
            "validation": {"passed": True},
        },
    )
    assert execute_one(
        database_url=database_url,
        worker_id="replacement-worker",
        stale_after_seconds=0,
    ) is True

    recovered = client.get(f"/api/v1/runs/{created['id']}").json()
    assert recovered["status"] == "succeeded"
    assert recovered["recovery_count"] == 1
    assert recovered["last_recovered_at"] is not None
    timeline = client.get(f"/api/v1/runs/{created['id']}/timeline").json()
    assert "run_recovered" in [event["event_type"] for event in timeline["events"]]
    app.state.database_engine.dispose()


def test_failed_validation_is_retained_as_degraded_and_cannot_be_approved(
    tmp_path: Path,
    monkeypatch,
):
    database_url = f"sqlite:///{(tmp_path / 'degraded.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    created = client.post("/api/v1/runs", json=request_body()).json()

    monkeypatch.setattr(
        "aggregator_demo.worker.optimize_day_ahead",
        lambda *_args, **_kwargs: {
            "solver_name": "validation-test",
            "validation": {
                "passed": False,
                "failed_checks": ["no_soc_shortfall"],
            },
        },
    )
    assert execute_one(database_url=database_url, worker_id="drill-worker") is True

    result = client.get(f"/api/v1/runs/{created['id']}/result").json()
    assert result["status"] == "degraded"
    assert result["result"]["validation"]["passed"] is False
    assert result["failure_code"] == "deterministic_validation_failed"
    approval = client.post(
        f"/api/v1/runs/{created['id']}/approval",
        json={"decision": "approved"},
    )
    assert approval.status_code == 409
    app.state.database_engine.dispose()
