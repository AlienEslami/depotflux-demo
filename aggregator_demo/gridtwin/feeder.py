from __future__ import annotations

from dataclasses import asdict, dataclass
from math import acos, tan
from typing import Sequence

import pandapower as pp
from pandapower.networks import create_cigre_network_mv


@dataclass(frozen=True)
class GridLimits:
    minimum_voltage_pu: float = 0.95
    maximum_voltage_pu: float = 1.05
    maximum_line_loading_percent: float = 100.0
    maximum_transformer_loading_percent: float = 100.0


@dataclass(frozen=True)
class FeederConfiguration:
    benchmark: str = "CIGRE MV distribution network"
    base_load_scale: float = 0.55
    depot_bus: int = 11
    bess_bus: int = 11
    depot_power_factor: float = 0.98


def build_feeder(configuration: FeederConfiguration = FeederConfiguration()):
    """Build the open CIGRE MV benchmark with named DepotFlux resources."""
    net = create_cigre_network_mv(with_der=False)
    net.load.loc[:, "scaling"] = configuration.base_load_scale
    depot_load = pp.create_load(
        net,
        bus=configuration.depot_bus,
        p_mw=0.0,
        q_mvar=0.0,
        name="DepotFlux EV depot import",
    )
    depot_export = pp.create_sgen(
        net,
        bus=configuration.depot_bus,
        p_mw=0.0,
        q_mvar=0.0,
        name="DepotFlux V2G export",
    )
    bess = pp.create_storage(
        net,
        bus=configuration.bess_bus,
        p_mw=0.0,
        max_e_mwh=0.5,
        sn_mva=0.25,
        min_e_mwh=0.05,
        name="GridTwin BESS",
    )
    net["gridtwin_assets"] = {
        "depot_load": int(depot_load),
        "depot_export": int(depot_export),
        "bess": int(bess),
    }
    return net


def run_power_flow(
    depot_power_kw: float,
    bess_power_kw: float = 0.0,
    *,
    base_load_scale: float | None = None,
    configuration: FeederConfiguration = FeederConfiguration(),
    limits: GridLimits = GridLimits(),
) -> dict:
    """Run one balanced AC power flow.

    Positive depot and BESS power consume energy. Negative values export it.
    """
    net = build_feeder(configuration)
    if base_load_scale is not None:
        original_loads = net.load.index.difference(
            [net.gridtwin_assets["depot_load"]]
        )
        net.load.loc[original_loads, "scaling"] = float(base_load_scale)
    depot_import_mw = max(0.0, float(depot_power_kw)) / 1000.0
    depot_export_mw = max(0.0, -float(depot_power_kw)) / 1000.0
    reactive_ratio = tan(acos(configuration.depot_power_factor))
    net.load.at[net.gridtwin_assets["depot_load"], "p_mw"] = depot_import_mw
    net.load.at[net.gridtwin_assets["depot_load"], "q_mvar"] = (
        depot_import_mw * reactive_ratio
    )
    net.sgen.at[net.gridtwin_assets["depot_export"], "p_mw"] = depot_export_mw
    net.storage.at[net.gridtwin_assets["bess"], "p_mw"] = (
        float(bess_power_kw) / 1000.0
    )
    # The inverter follows the depot's 0.98 power factor in this educational
    # model, so active-power support does not leave the original reactive load
    # untouched and silently violate the voltage envelope.
    net.storage.at[net.gridtwin_assets["bess"], "q_mvar"] = (
        float(bess_power_kw) / 1000.0 * reactive_ratio
    )
    pp.runpp(
        net,
        algorithm="nr",
        calculate_voltage_angles=False,
        check_connectivity=True,
        init="auto",
        numba=False,
    )

    bus_voltage = net.res_bus.vm_pu.dropna()
    line_loading = net.res_line.loading_percent.dropna()
    transformer_loading = net.res_trafo.loading_percent.dropna()
    low_voltage = bus_voltage[bus_voltage < limits.minimum_voltage_pu]
    high_voltage = bus_voltage[bus_voltage > limits.maximum_voltage_pu]
    line_overloads = line_loading[
        line_loading > limits.maximum_line_loading_percent
    ]
    transformer_overloads = transformer_loading[
        transformer_loading > limits.maximum_transformer_loading_percent
    ]
    losses_mw = float(net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum())
    return {
        "converged": bool(net.converged),
        "minimum_voltage_pu": float(bus_voltage.min()),
        "maximum_voltage_pu": float(bus_voltage.max()),
        "maximum_line_loading_percent": float(line_loading.max()),
        "maximum_transformer_loading_percent": float(transformer_loading.max()),
        "feeder_import_kw": float(net.res_ext_grid.p_mw.sum() * 1000.0),
        "losses_kw": losses_mw * 1000.0,
        "low_voltage_bus_count": int(len(low_voltage)),
        "high_voltage_bus_count": int(len(high_voltage)),
        "line_overload_count": int(len(line_overloads)),
        "transformer_overload_count": int(len(transformer_overloads)),
        "voltage_violation": bool(len(low_voltage) or len(high_voltage)),
        "thermal_violation": bool(len(line_overloads) or len(transformer_overloads)),
    }


def hosting_limit_kw(
    *,
    base_load_scale: float = FeederConfiguration().base_load_scale,
    upper_bound_kw: float = 2500.0,
    safety_margin: float = 0.98,
    tolerance_kw: float = 0.5,
) -> float:
    """Find a conservative depot import envelope from repeated AC power flow."""
    lower = 0.0
    upper = upper_bound_kw
    while upper - lower > tolerance_kw:
        candidate = (lower + upper) / 2.0
        result = run_power_flow(candidate, base_load_scale=base_load_scale)
        if result["voltage_violation"] or result["thermal_violation"]:
            upper = candidate
        else:
            lower = candidate
    return round(lower * safety_margin, 3)


def evaluate_schedule(
    depot_power_kw: Sequence[float],
    bess_power_kw: Sequence[float],
    *,
    interval_hours: float,
    base_load_scale: float | Sequence[float] = FeederConfiguration().base_load_scale,
) -> dict:
    if len(depot_power_kw) != len(bess_power_kw):
        raise ValueError("depot and BESS schedules must have the same horizon")
    scales = (
        [float(base_load_scale)] * len(depot_power_kw)
        if isinstance(base_load_scale, (int, float))
        else [float(value) for value in base_load_scale]
    )
    if len(scales) != len(depot_power_kw):
        raise ValueError("base-load profile must cover the schedule horizon")

    intervals = [
        run_power_flow(depot, bess, base_load_scale=scale)
        for depot, bess, scale in zip(depot_power_kw, bess_power_kw, scales)
    ]
    voltage_intervals = sum(row["voltage_violation"] for row in intervals)
    thermal_intervals = sum(row["thermal_violation"] for row in intervals)
    return {
        "intervals": intervals,
        "minimum_voltage_pu": min(row["minimum_voltage_pu"] for row in intervals),
        "maximum_voltage_pu": max(row["maximum_voltage_pu"] for row in intervals),
        "maximum_line_loading_percent": max(
            row["maximum_line_loading_percent"] for row in intervals
        ),
        "maximum_transformer_loading_percent": max(
            row["maximum_transformer_loading_percent"] for row in intervals
        ),
        "energy_losses_kwh": sum(row["losses_kw"] for row in intervals)
        * interval_hours,
        "voltage_violation_intervals": int(voltage_intervals),
        "voltage_violation_duration_hours": voltage_intervals * interval_hours,
        "thermal_violation_intervals": int(thermal_intervals),
        "thermal_violation_duration_hours": thermal_intervals * interval_hours,
        "voltage_violation_bus_samples": sum(
            row["low_voltage_bus_count"] + row["high_voltage_bus_count"]
            for row in intervals
        ),
        "thermal_violation_element_samples": sum(
            row["line_overload_count"] + row["transformer_overload_count"]
            for row in intervals
        ),
        "limits": asdict(GridLimits()),
    }
