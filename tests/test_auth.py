from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.auth import AuthConfig, AuthMode, AuthenticationError, Role
from aggregator_demo.settings import RuntimeSettings


def api_key_environment() -> dict[str, str]:
    return {
        "DEMO_AUTH_MODE": "api_key",
        "DEMO_OPERATOR_API_KEY": "operator-key-000000000000",
        "DEMO_APPROVER_API_KEY": "approver-key-000000000000",
        "DEMO_AUDITOR_API_KEY": "auditor-key-0000000000000",
        "DEMO_ADMIN_API_KEY": "admin-key-0000000000000000",
    }


def bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key_environment()[f'DEMO_{role.upper()}_API_KEY']}"}


def test_api_key_configuration_requires_unique_strong_keys() -> None:
    incomplete = {"DEMO_AUTH_MODE": "api_key"}
    with pytest.raises(ValueError, match="DEMO_OPERATOR_API_KEY"):
        AuthConfig.from_environment(incomplete)

    duplicate = api_key_environment()
    duplicate["DEMO_APPROVER_API_KEY"] = duplicate["DEMO_OPERATOR_API_KEY"]
    with pytest.raises(ValueError, match="unique"):
        AuthConfig.from_environment(duplicate)


def test_authentication_maps_keys_to_fixed_roles() -> None:
    config = AuthConfig.from_environment(api_key_environment())
    principal = config.authenticate(bearer("operator")["Authorization"])
    assert principal.subject == "depotflux-operator"
    assert principal.role is Role.OPERATOR
    with pytest.raises(AuthenticationError) as exc_info:
        config.authenticate("Bearer invalid-but-long-enough")
    assert exc_info.value.status_code == 401


def test_api_enforces_role_separation(tmp_path) -> None:
    settings = RuntimeSettings.from_environment(api_key_environment())
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'rbac.db'}",
        initialize_schema=True,
        runtime_settings=settings,
    )
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        meta = client.get("/api/v1/meta").json()
        assert meta["authentication_mode"] == AuthMode.API_KEY.value

        unauthorized = client.get("/api/v1/inputs")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["code"] == "authentication_required"

        invalid_request = client.post(
            "/api/v1/runs",
            headers=bearer("operator"),
            json={"run_type": "not-a-run-type"},
        )
        assert invalid_request.status_code == 422
        assert invalid_request.json()["code"] == "request_validation_failed"
        assert "input" not in invalid_request.json()

        inputs = client.get("/api/v1/inputs", headers=bearer("operator"))
        assert inputs.status_code == 200
        selected = inputs.json()["items"][0]
        created = client.post(
            "/api/v1/runs",
            headers={**bearer("operator"), "Idempotency-Key": "rbac-run"},
            json={
                "run_type": "day_ahead",
                "optimization_mode": "selfish",
                "input_reference": selected["reference"],
                "input_sha256": selected["sha256"],
                "v2g_enabled": True,
                "agent_backend": "rule",
                "scenario_ids": ["nominal"],
            },
        )
        assert created.status_code == 202
        UUID(created.json()["id"])
        assert created.json()["requested_by"] == "depotflux-operator"

        forbidden = client.post(
            f"/api/v1/runs/{created.json()['id']}/approval",
            headers=bearer("operator"),
            json={"decision": "approved"},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["code"] == "insufficient_role"

        session = client.get("/api/v1/session", headers=bearer("auditor"))
        assert session.status_code == 200
        assert session.json() == {
            "subject": "depotflux-auditor",
            "role": "auditor",
            "authentication_mode": "api_key",
        }
