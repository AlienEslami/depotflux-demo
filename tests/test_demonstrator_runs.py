from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from aggregator_demo.app import create_app
from aggregator_demo.contracts import RunCreateRequest, RunStatus
from aggregator_demo.input_registry import DemoInputRegistry
from aggregator_demo.run_repository import RunConflictError, RunRepository


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


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'demo.db').as_posix()}"


@pytest.fixture
def app(database_url: str):
    return create_app(database_url=database_url, initialize_schema=True)


def test_submit_get_and_list_persisted_run(app):
    client = TestClient(app)

    submitted = client.post(
        "/api/v1/runs",
        json=request_body(),
        headers={"X-Operator-ID": "dispatcher@example.test"},
    )

    assert submitted.status_code == 202
    created = submitted.json()
    assert created["status"] == "queued"
    assert created["requested_by"] == "dispatcher@example.test"
    run_id = UUID(created["id"])

    fetched = client.get(f"/api/v1/runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json() == created

    listed = client.get("/api/v1/runs?limit=10&offset=0")
    assert listed.status_code == 200
    assert listed.json()["items"] == [created]


def test_submission_is_idempotent_for_same_key_and_payload(app):
    client = TestClient(app)
    headers = {"Idempotency-Key": "day-ahead-demo-001"}

    first = client.post("/api/v1/runs", json=request_body(), headers=headers)
    second = client.post("/api/v1/runs", json=request_body(), headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]


def test_idempotency_key_rejects_different_payload(app):
    client = TestClient(app)
    headers = {"Idempotency-Key": "day-ahead-demo-002"}
    client.post("/api/v1/runs", json=request_body(), headers=headers)

    conflict = client.post(
        "/api/v1/runs",
        json=request_body(optimization_mode="altruistic"),
        headers=headers,
    )

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"


def test_queued_run_can_be_cancelled_idempotently(app):
    client = TestClient(app)
    created = client.post("/api/v1/runs", json=request_body()).json()

    first = client.post(f"/api/v1/runs/{created['id']}/cancel")
    second = client.post(f"/api/v1/runs/{created['id']}/cancel")

    assert first.status_code == 200
    assert first.json()["status"] == "cancelled"
    assert first.json()["completed_at"] is not None
    assert second.json()["status"] == "cancelled"


def test_invalid_contract_is_rejected_before_persistence(app):
    client = TestClient(app)

    invalid = client.post(
        "/api/v1/runs",
        json=request_body(input_sha256="not-a-hash", unexpected=True),
    )

    assert invalid.status_code == 422
    assert client.get("/api/v1/runs").json()["items"] == []


def test_registered_inputs_are_discoverable_and_hash_verified(app):
    client = TestClient(app)

    inputs = client.get("/api/v1/inputs")
    assert inputs.status_code == 200
    assert [item["fleet_size"] for item in inputs.json()["items"]] == [8, 16, 32]

    unknown = client.post(
        "/api/v1/runs",
        json=request_body(input_reference="demo/not-registered"),
    )
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "input_reference_unknown"

    mismatched = client.post(
        "/api/v1/runs",
        json=request_body(input_sha256="a" * 64),
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["code"] == "input_integrity_error"
    assert client.get("/api/v1/runs").json()["items"] == []


def test_runs_survive_application_restart(database_url: str):
    first_app = create_app(database_url=database_url, initialize_schema=True)
    created = TestClient(first_app).post(
        "/api/v1/runs", json=request_body()
    ).json()
    first_app.state.database_engine.dispose()

    second_app = create_app(database_url=database_url, initialize_schema=False)
    fetched = TestClient(second_app).get(f"/api/v1/runs/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
    second_app.state.database_engine.dispose()


def test_readiness_requires_the_migrated_run_schema(database_url: str):
    unmigrated_app = create_app(database_url=database_url, initialize_schema=False)

    response = TestClient(unmigrated_app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["detail"] == "database unavailable"
    unmigrated_app.state.database_engine.dispose()


def test_repository_enforces_lifecycle_transitions(app):
    request = RunCreateRequest.model_validate(request_body())
    with app.state.session_factory() as session:
        repository = RunRepository(session)
        created, _ = repository.create(
            request,
            requested_by="worker-test",
            idempotency_key=None,
        )
        running = repository.transition(created.id, RunStatus.RUNNING)
        succeeded = repository.transition(created.id, RunStatus.SUCCEEDED)

        assert running.started_at is not None
        assert succeeded.completed_at is not None
        with pytest.raises(RunConflictError):
            repository.transition(created.id, RunStatus.RUNNING)


def test_initial_alembic_migration_builds_run_table(tmp_path: Path):
    database_path = tmp_path / "migrated.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, "head")

    migrated_app = create_app(
        database_url=f"sqlite:///{database_path.as_posix()}",
        initialize_schema=False,
    )
    inspector = inspect(migrated_app.state.database_engine)
    assert "optimization_runs" in inspector.get_table_names()
    assert "operator_approvals" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("optimization_runs")}
    assert {
        "id",
        "status",
        "request_fingerprint",
        "completed_at",
        "worker_id",
        "result_payload",
    } <= columns
    migrated_app.state.database_engine.dispose()
