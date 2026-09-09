from __future__ import annotations

from copy import deepcopy

from aggregator_demo.gridtwin.security import AuditTrail, run_security_experiment


def _experiment_fixture():
    unsafe_interval = {
        "minimum_voltage_pu": 0.945,
        "voltage_violation": True,
        "thermal_violation": False,
    }
    safe_interval = {
        "minimum_voltage_pu": 0.952,
        "voltage_violation": False,
        "thermal_violation": False,
    }
    return {
        "grid": {
            "hosting_limit_kw": 1370.0,
            "limits": {"minimum_voltage_pu": 0.95},
        },
        "scenarios": {
            "cost_optimized": {
                "site_power_kw": [1600.0],
                "metrics": {"energy_cost_cad": 100.0},
                "power_flow": {"intervals": [unsafe_interval]},
            },
            "grid_constrained": {
                "site_power_kw": [1370.0],
                "metrics": {"energy_cost_cad": 101.0},
                "power_flow": {
                    "intervals": [safe_interval],
                    "voltage_violation_intervals": 0,
                    "thermal_violation_intervals": 0,
                },
            },
        },
    }


def test_attacks_are_detected_denied_audited_and_recovered():
    result = run_security_experiment(_experiment_fixture())

    assert result["false_data_injection"]["detected"] is True
    assert result["false_data_injection"]["remaining_violations"] == 0
    assert result["unauthorized_setpoint"]["detected"] is True
    assert result["unauthorized_setpoint"]["denied"] is True
    assert (
        result["unauthorized_setpoint"]["gateway_policy_code"]
        == "gateway_authentication_failed"
    )
    assert result["unauthorized_setpoint"]["physical_constraint_alert"] is True
    assert result["unauthorized_setpoint"]["modbus_write_attempts"] == 0
    assert result["unauthorized_setpoint"]["modbus_read_attempts"] == 0
    assert result["unauthorized_setpoint"]["frame_transmitted"] is False
    assert result["detection_metrics"]["precision"] == 1.0
    assert result["detection_metrics"]["recall"] == 1.0
    assert result["audit_chain_valid"] is True


def test_audit_chain_detects_tampering():
    trail = AuditTrail()
    trail.append("telemetry", "accepted", {"voltage_pu": 1.0})
    trail.append("command", "rejected", {"setpoint_kw": 2000.0})
    tampered = deepcopy(trail.records)

    assert trail.verify() is True
    trail.records[0]["details"]["voltage_pu"] = 0.5
    assert trail.verify() is False
    assert tampered[0]["details"]["voltage_pu"] == 1.0
