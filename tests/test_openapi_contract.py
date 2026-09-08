from __future__ import annotations

from aggregator_demo.app import app


def test_openapi_contract_declares_versioned_routes_and_bearer_auth() -> None:
    schema = app.openapi()
    assert schema["info"]["version"] == "0.1.0"
    assert "/api/v1/runs" in schema["paths"]
    assert "/api/v1/session" in schema["paths"]
    assert "/api/v1/runs/{run_id}/dispatch-simulations" in schema["paths"]
    schemes = schema["components"]["securitySchemes"]
    assert schemes["HTTPBearer"]["scheme"] == "bearer"
