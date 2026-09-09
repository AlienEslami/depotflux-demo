from __future__ import annotations

import pytest

from aggregator_demo.gridtwin.feeder import (
    build_feeder,
    evaluate_schedule,
    hosting_limit_kw,
    run_power_flow,
)


def test_cigre_feeder_contains_named_depot_and_bess():
    net = build_feeder()

    assert net.bus.at[11, "name"] == "Bus 11"
    assert net.load.at[net.gridtwin_assets["depot_load"], "name"] == (
        "DepotFlux EV depot import"
    )
    assert net.storage.at[net.gridtwin_assets["bess"], "name"] == "GridTwin BESS"
    assert net.storage.at[net.gridtwin_assets["bess"], "max_e_mwh"] == 0.5


def test_documented_scaled_cigre_base_case_is_stable():
    result = run_power_flow(0.0, 0.0)

    assert result["converged"] is True
    assert result["minimum_voltage_pu"] == pytest.approx(0.9783, abs=0.0005)
    assert result["maximum_line_loading_percent"] == pytest.approx(50.0, abs=0.2)
    assert result["maximum_transformer_loading_percent"] == pytest.approx(
        54.19, abs=0.2
    )
    assert result["voltage_violation"] is False
    assert result["thermal_violation"] is False


def test_hosting_limit_separates_unsafe_and_conservative_imports():
    limit = hosting_limit_kw()

    assert 1300.0 < limit < 1500.0
    assert run_power_flow(limit)["voltage_violation"] is False
    assert run_power_flow(1600.0)["voltage_violation"] is True


def test_schedule_reports_violation_durations_and_energy_losses():
    result = evaluate_schedule(
        [1600.0, 0.0],
        [0.0, 0.0],
        interval_hours=0.5,
    )

    assert result["voltage_violation_intervals"] == 1
    assert result["voltage_violation_duration_hours"] == 0.5
    assert result["thermal_violation_intervals"] == 0
    assert result["energy_losses_kwh"] > 0
