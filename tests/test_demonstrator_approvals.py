from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.input_registry import DemoInputRegistry
from aggregator_demo.run_repository import RunRepository


DEMO_INPUT = DemoInputRegistry().descriptor("demo/depot-a-8-v1")


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


def test_successful_candidate_receives_one_immutable_operator_decision(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'approval.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    created = client.post(
        "/api/v1/runs",
        json=request_body(),
        headers={"X-Operator-ID": "planner@example.test"},
    ).json()
    run_id = UUID(created["id"])

    premature = client.post(
        f"/api/v1/runs/{run_id}/approval",
        json={"decision": "approved"},
    )
    assert premature.status_code == 409
    assert premature.json()["code"] == "approval_conflict"

    with app.state.session_factory() as session:
        repository = RunRepository(session)
        claimed = repository.claim_next(worker_id="approval-test-worker")
        assert claimed is not None
        repository.complete(
            run_id,
            {
                "solver_name": "appsi_highs",
                "validation": {"passed": True, "checks": ["test"]},
            },
        )

    decision_payload = {
        "decision": "approved",
        "note": "  Checked against the morning pull-out requirement.  ",
    }
    headers = {"X-Operator-ID": "supervisor@example.test"}
    approved = client.post(
        f"/api/v1/runs/{run_id}/approval",
        json=decision_payload,
        headers=headers,
    )
    repeated = client.post(
        f"/api/v1/runs/{run_id}/approval",
        json={
            "decision": "approved",
            "note": "Checked against the morning pull-out requirement.",
        },
        headers=headers,
    )

    assert approved.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json() == approved.json()
    assert approved.json()["decision"] == "approved"
    assert approved.json()["decided_by"] == "supervisor@example.test"
    assert approved.json()["result_sha256"]
    assert approved.json()["note"] == "Checked against the morning pull-out requirement."

    fetched = client.get(f"/api/v1/runs/{run_id}/approval")
    assert fetched.json() == approved.json()

    changed = client.post(
        f"/api/v1/runs/{run_id}/approval",
        json={"decision": "rejected", "note": "Changed my mind."},
        headers=headers,
    )
    assert changed.status_code == 409
    assert changed.json()["code"] == "approval_conflict"

    timeline = client.get(f"/api/v1/runs/{run_id}/timeline")
    assert timeline.status_code == 200
    assert [event["event_type"] for event in timeline.json()["events"]] == [
        "run_submitted",
        "run_started",
        "run_completed",
        "decision_recorded",
    ]
    assert timeline.json()["events"][-1]["actor"] == "supervisor@example.test"
    app.state.database_engine.dispose()


def test_candidate_without_passing_validation_cannot_be_approved(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'invalid-result.db').as_posix()}"
    app = create_app(database_url=database_url, initialize_schema=True)
    client = TestClient(app)
    run_id = UUID(client.post("/api/v1/runs", json=request_body()).json()["id"])

    with app.state.session_factory() as session:
        repository = RunRepository(session)
        assert repository.claim_next(worker_id="approval-test-worker") is not None
        repository.complete(
            run_id,
            {"solver_name": "appsi_highs", "validation": {"passed": False}},
        )

    response = client.post(
        f"/api/v1/runs/{run_id}/approval",
        json={"decision": "approved"},
    )
    assert response.status_code == 409
    assert "passing deterministic validation" in response.json()["message"]
    app.state.database_engine.dispose()
