from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.contracts import RunStatus


def test_liveness_contract():
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "service": "agentic-aggregator-api",
        "status": "ok",
        "version": "0.1.0",
    }


def test_capabilities_publish_operating_boundary_and_statuses():
    client = TestClient(create_app())

    response = client.get("/api/v1/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    assert body["operating_boundary"] == "human_approved_decision_support"
    assert body["direct_asset_control"] is False
    assert body["run_statuses"] == [status.value for status in RunStatus]


def test_only_completed_lifecycle_states_are_terminal():
    assert RunStatus.QUEUED.is_terminal is False
    assert RunStatus.RUNNING.is_terminal is False
    assert RunStatus.CANCEL_REQUESTED.is_terminal is False
    assert RunStatus.SUCCEEDED.is_terminal is True
    assert RunStatus.FAILED.is_terminal is True
    assert RunStatus.INFEASIBLE.is_terminal is True
    assert RunStatus.TIMED_OUT.is_terminal is True
    assert RunStatus.CANCELLED.is_terminal is True
    assert RunStatus.DEGRADED.is_terminal is True


def test_dashboard_origin_is_allowed_to_call_the_api():
    client = TestClient(create_app())

    response = client.options(
        "/api/v1/inputs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
