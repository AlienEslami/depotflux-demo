from __future__ import annotations

from fastapi.testclient import TestClient

from aggregator_demo.app import create_app


def _runner(reference: str, *, include_security: bool):
    return {
        "experiment_id": "stub-gridtwin",
        "input_reference": reference,
        "security": {
            "false_data_injection": {"detected": True},
            "unauthorized_setpoint": {"denied": True},
            "audit_chain_valid": True,
        },
        "include_security": include_security,
    }


def test_gridtwin_meta_preserves_software_only_boundary(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{(tmp_path / 'gridtwin-meta.db').as_posix()}",
        initialize_schema=True,
        gridtwin_runner=_runner,
    )
    response = TestClient(app).get("/api/v1/gridtwin/meta")

    assert response.status_code == 200
    assert response.json()["synthetic_only"] is True
    assert response.json()["direct_asset_control"] is False
    assert response.json()["scenarios"] == [
        "uncontrolled",
        "cost_optimized",
        "grid_constrained",
    ]
    app.state.database_engine.dispose()


def test_gridtwin_experiment_and_attack_routes_use_runner(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{(tmp_path / 'gridtwin-run.db').as_posix()}",
        initialize_schema=True,
        gridtwin_runner=_runner,
    )
    client = TestClient(app)

    experiment = client.post(
        "/api/v1/gridtwin/experiments",
        json={"input_reference": "demo/depot-a-8-v1", "include_security": False},
    )
    attack = client.post(
        "/api/v1/gridtwin/attacks/simulate",
        json={"attack_type": "unauthorized_setpoint"},
    )

    assert experiment.status_code == 200
    assert experiment.json()["include_security"] is False
    assert attack.status_code == 200
    assert attack.json()["result"] == {"denied": True}
    assert attack.json()["audit_chain_valid"] is True
    app.state.database_engine.dispose()
