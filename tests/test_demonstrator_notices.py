from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.input_registry import DemoInputRegistry
from aggregator_demo.worker import execute_one


DEMO_INPUT = DemoInputRegistry().descriptor("demo/depot-a-8-v1")


def day_ahead_request():
    return {
        "run_type": "day_ahead",
        "optimization_mode": "selfish",
        "input_reference": DEMO_INPUT.reference,
        "input_sha256": DEMO_INPUT.sha256,
        "v2g_enabled": True,
        "agent_backend": "rule",
        "scenario_ids": ["nominal"],
    }


def _approved_baseline(client: TestClient, database_url: str, monkeypatch) -> str:
    baseline_id = client.post("/api/v1/runs", json=day_ahead_request()).json()["id"]
    monkeypatch.setenv("DA_SOLVER_ORDER", "appsi_highs,highs")
    assert execute_one(database_url=database_url, worker_id="baseline-worker") is True
    approval = client.post(
        f"/api/v1/runs/{baseline_id}/approval",
        json={"decision": "approved", "note": "Frozen operating baseline."},
        headers={"X-Operator-ID": "supervisor@example.test"},
    )
    assert approval.status_code == 201
    return baseline_id


def test_simulated_notice_queues_auditable_remaining_horizon_run(
    tmp_path: Path,
    monkeypatch,
):
    database_url = f"sqlite:///{(tmp_path / 'notices.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    baseline_id = _approved_baseline(client, database_url, monkeypatch)

    headers = {
        "Idempotency-Key": "compound-demo-001",
        "X-Operator-ID": "dispatcher@example.test",
    }
    payload = {
        "baseline_run_id": baseline_id,
        "scenario": "combined_disruption",
    }
    created = client.post("/api/v1/notices/simulate", json=payload, headers=headers)
    repeated = client.post("/api/v1/notices/simulate", json=payload, headers=headers)

    assert created.status_code == 202
    assert repeated.status_code == 202
    notice = created.json()
    assert repeated.json() == notice
    assert notice["source"] == "simulator"
    assert notice["interpretation_backend"] == "rule"
    assert notice["replan_recommended"] is True
    assert notice["structured_facts"]["late_returns"][0]["delay_minutes"] == 30
    assert notice["structured_facts"]["charger_deratings"][0]["to_kw"] == 150.0

    candidate = client.get(f"/api/v1/runs/{notice['candidate_run_id']}")
    assert candidate.status_code == 200
    assert candidate.json()["run_type"] == "real_time"
    assert candidate.json()["scenario_ids"] == ["notice:combined_disruption"]

    linked = client.get(f"/api/v1/runs/{notice['candidate_run_id']}/notice")
    assert linked.json() == notice
    listed = client.get("/api/v1/notices")
    assert listed.json()["items"] == [notice]

    monkeypatch.setenv("RT_SOLVER_ORDER", "appsi_highs,highs")
    monkeypatch.setenv("RT_SOLVER_TIME_LIMIT", "30")
    monkeypatch.setenv("RT_SOLVER_MIP_GAP", "0.05")
    assert execute_one(database_url=database_url, worker_id="replan-worker") is True
    result_response = client.get(
        f"/api/v1/runs/{notice['candidate_run_id']}/result"
    )
    assert result_response.status_code == 200
    result_body = result_response.json()
    assert result_body["status"] == "succeeded", result_body
    result = result_body["result"]
    assert result["run_type"] == "real_time"
    assert result["remaining_horizon_start"] == 15
    assert result["optimized_steps"] == 34
    assert result["validation"]["passed"] is True
    assert result["comparison"]["baseline_run_id"] == baseline_id
    assert result["comparison"]["changed_intervals"] > 0
    assert result["notice"]["notice_id"] == notice["id"]

    timeline = client.get(
        f"/api/v1/runs/{notice['candidate_run_id']}/timeline"
    ).json()["events"]
    assert "notice_received" in [event["event_type"] for event in timeline]
    app.state.database_engine.dispose()


def test_notice_requires_an_approved_baseline(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'unapproved.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    baseline_id = client.post("/api/v1/runs", json=day_ahead_request()).json()["id"]

    response = client.post(
        "/api/v1/notices/simulate",
        json={"baseline_run_id": baseline_id, "scenario": "late_return"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "notice_conflict"
    assert "approved candidate" in response.json()["message"]
    assert client.get("/api/v1/notices").json()["items"] == []
    app.state.database_engine.dispose()
