from __future__ import annotations

import pytest

from aggregator_demo.gridtwin.dispatch import (
    BessConfiguration,
    optimize_bess_dispatch,
    uncontrolled_charging_schedule,
)


def test_uncontrolled_charging_is_earliest_available_and_energy_preserving():
    schedule = uncontrolled_charging_schedule(
        1600.0,
        4,
        interval_hours=0.5,
        site_capacity_kw=1600.0,
    )

    assert schedule == [1600.0, 1600.0, 0.0, 0.0]
    assert sum(schedule) * 0.5 == 1600.0


def test_bess_dispatch_respects_grid_envelope_and_terminal_soc(monkeypatch):
    monkeypatch.setenv("GRIDTWIN_SOLVER_ORDER", "appsi_highs,highs")
    config = BessConfiguration(
        capacity_kwh=500.0,
        maximum_charge_kw=250.0,
        maximum_discharge_kw=250.0,
        initial_soc=0.5,
        final_soc=0.5,
    )
    result = optimize_bess_dispatch(
        [1600.0, 0.0, 0.0, 0.0],
        [0.10, 0.20, 0.05, 0.20],
        [0.07, 0.15, 0.03, 0.15],
        interval_hours=0.5,
        configuration=config,
        maximum_site_import_kw=1400.0,
    )

    assert max(result["site_power_kw"]) <= 1400.0 + 1e-7
    assert result["energy_kwh"][0] == pytest.approx(250.0)
    assert result["energy_kwh"][-1] == pytest.approx(250.0)
    assert result["throughput_kwh"] > 0
    assert result["solver_termination"] == "optimal"
