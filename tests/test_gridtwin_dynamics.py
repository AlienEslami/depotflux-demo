from __future__ import annotations

import numpy as np
import pytest

from aggregator_demo.gridtwin.dynamics import (
    DynamicParameters,
    SCENARIOS,
    analytical_two_bus_voltage_pu,
    run_step_sensitivity,
    schedule_feedback,
    simulate,
    solve_operating_point,
)


CHARGER_POWER_KW = 1600.0
INVERTER_INJECTION_KW = 228.455


def test_operating_point_matches_closed_form_two_bus_baseline():
    parameters = DynamicParameters()
    analytical = analytical_two_bus_voltage_pu(
        CHARGER_POWER_KW, INVERTER_INJECTION_KW, parameters=parameters
    )
    numerical = solve_operating_point(
        CHARGER_POWER_KW,
        INVERTER_INJECTION_KW,
        parameters=parameters,
        include_pcc_capacitance=False,
    )
    numerical_pu = (
        abs(numerical["voltage_phase_rms"]) / parameters.phase_voltage_rms_v
    )

    assert numerical["residual_v"] <= 1.0e-6
    assert numerical_pu == pytest.approx(analytical, abs=1.0e-8)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.key)
def test_required_dynamic_scenarios_are_stable_and_meet_declared_criteria(scenario):
    result = simulate(
        scenario,
        charger_power_kw=CHARGER_POWER_KW,
        inverter_injection_kw=INVERTER_INJECTION_KW,
        step_s=25.0e-6,
    )

    assert result.criteria["passed"] is True
    assert result.metrics["finite_state"] is True
    assert result.metrics["recovery_time_s"] is not None
    assert result.metrics["peak_active_power_kw"] > result.metrics["minimum_active_power_kw"]
    assert result.metrics["peak_absolute_reactive_power_kvar"] > 0.0
    assert np.isfinite(result.frequency_hz).any()


def test_selected_solver_step_and_finer_steps_match_reference():
    sensitivity, _ = run_step_sensitivity(
        charger_power_kw=CHARGER_POWER_KW,
        inverter_injection_kw=INVERTER_INJECTION_KW,
    )

    assert sensitivity["selected_step_s"] == 25.0e-6
    assert sensitivity["passed"] is True
    for scenario in sensitivity["scenarios"].values():
        selected_or_finer = [
            row
            for row in scenario["runs"]
            if row["candidate_step_s"] <= sensitivity["selected_step_s"]
        ]
        assert selected_or_finer
        assert all(row["passed"] for row in selected_or_finer)


def test_contingency_violation_returns_bounded_reschedule_feedback():
    feedback = schedule_feedback(
        [0.0, CHARGER_POWER_KW, 800.0],
        [0.0, -INVERTER_INJECTION_KW, 0.0],
        schedule_limit_kw=1371.545,
    )

    assert feedback["selected_interval_index"] == 1
    assert feedback["passed"] is False
    assert feedback["workflow_action"] == "request_reschedule"
    assert feedback["recommended_maximum_depot_import_kw"] == pytest.approx(1371.545)
    assert feedback["contingency_final_voltage_pu"] < feedback[
        "contingency_minimum_voltage_requirement_pu"
    ]
    facts = feedback["replanning_structured_facts"]
    assert facts["effective_from_timestep"] == 15
    assert len(facts["charger_deratings"]) == 8
    assert sum(item["to_kw"] for item in facts["charger_deratings"]) == pytest.approx(
        1371.545
    )


def test_dynamic_fixture_is_deterministic():
    first = simulate(
        "normal_load_change",
        charger_power_kw=CHARGER_POWER_KW,
        inverter_injection_kw=INVERTER_INJECTION_KW,
        step_s=50.0e-6,
    )
    second = simulate(
        "normal_load_change",
        charger_power_kw=CHARGER_POWER_KW,
        inverter_injection_kw=INVERTER_INJECTION_KW,
        step_s=50.0e-6,
    )

    np.testing.assert_array_equal(first.states, second.states)
