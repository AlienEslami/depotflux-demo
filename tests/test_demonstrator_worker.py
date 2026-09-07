from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.input_registry import DemoInputRegistry
from aggregator_demo.worker import execute_one


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


def test_worker_records_an_explicit_failure_for_unsupported_run_type(tmp_path: Path):
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
    assert result.json()["failure_code"] == "unsupported_run_configuration"
    assert result.json()["result"] is None
    app.state.database_engine.dispose()
