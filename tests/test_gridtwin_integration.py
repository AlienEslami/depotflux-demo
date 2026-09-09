from __future__ import annotations

from aggregator_demo.gridtwin.service import run_evidence_sprint


def test_full_evidence_sprint_reuses_optimizer_and_clears_grid_violations(monkeypatch):
    monkeypatch.setenv("DA_SOLVER_ORDER", "appsi_highs,highs")
    monkeypatch.setenv("GRIDTWIN_SOLVER_ORDER", "appsi_highs,highs")

    evidence = run_evidence_sprint()

    scenarios = evidence["scenarios"]
    assert scenarios["uncontrolled"]["power_flow"][
        "voltage_violation_intervals"
    ] > 0
    assert scenarios["cost_optimized"]["power_flow"][
        "voltage_violation_intervals"
    ] > 0
    assert scenarios["grid_constrained"]["power_flow"][
        "voltage_violation_intervals"
    ] == 0
    assert scenarios["grid_constrained"]["power_flow"][
        "thermal_violation_intervals"
    ] == 0
    assert evidence["security"]["false_data_injection"]["detected"] is True
    assert evidence["security"]["unauthorized_setpoint"]["denied"] is True
    assert evidence["security"]["audit_chain_valid"] is True
