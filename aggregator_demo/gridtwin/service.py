from __future__ import annotations

import io
import time
from contextlib import redirect_stdout
from importlib.metadata import version

from ..input_registry import DemoInputRegistry
from ..optimizer_service import optimize_day_ahead
from .dispatch import (
    BessConfiguration,
    optimize_bess_dispatch,
    uncontrolled_charging_schedule,
)
from .feeder import FeederConfiguration, GridLimits, evaluate_schedule, hosting_limit_kw, run_power_flow
from .security import run_security_experiment


DEFAULT_INPUT_REFERENCE = "demo/depot-a-8-v1"


def run_evidence_sprint(
    input_reference: str = DEFAULT_INPUT_REFERENCE,
    *,
    include_security: bool = True,
) -> dict:
    """Run the deterministic three-scenario GridTwin evidence experiment."""
    total_started = time.perf_counter()
    registry = DemoInputRegistry()
    descriptor = registry.descriptor(input_reference)
    input_data = registry.load(descriptor.reference, descriptor.sha256)
    interval_hours = float(input_data.get("timestep_minutes", 30.0)) / 60.0
    buy_prices = [float(row["buy_price"]) for row in input_data["tariffs"]]
    sell_prices = [float(row["sell_price"]) for row in input_data["tariffs"]]

    optimizer_started = time.perf_counter()
    optimizer_log = io.StringIO()
    with redirect_stdout(optimizer_log):
        depot_result = optimize_day_ahead(
            input_data,
            optimization_mode="selfish",
            v2g_enabled=True,
            solver_mip_gap=0.0,
        )
    depot_solve_seconds = time.perf_counter() - optimizer_started
    depot_power_kw = [
        (buy - sell) / interval_hours
        for buy, sell in zip(depot_result["w_buy"], depot_result["w_sell"])
    ]
    required_energy_kwh = sum(depot_result["w_buy"]) - sum(
        depot_result["w_sell"]
    )
    uncontrolled_power_kw = uncontrolled_charging_schedule(
        required_energy_kwh,
        len(depot_power_kw),
        interval_hours=interval_hours,
        site_capacity_kw=1600.0,
    )
    envelope_kw = hosting_limit_kw()

    cost_bess = optimize_bess_dispatch(
        depot_power_kw,
        buy_prices,
        sell_prices,
        interval_hours=interval_hours,
    )
    constrained_bess = optimize_bess_dispatch(
        depot_power_kw,
        buy_prices,
        sell_prices,
        interval_hours=interval_hours,
        maximum_site_import_kw=envelope_kw,
    )
    scenarios = {
        "uncontrolled": _scenario_result(
            name="Uncontrolled charging",
            depot_power_kw=uncontrolled_power_kw,
            bess_power_kw=[0.0] * len(uncontrolled_power_kw),
            buy_prices=buy_prices,
            sell_prices=sell_prices,
            interval_hours=interval_hours,
            aggregator_margin_cad=0.0,
            battery_throughput_kwh=0.0,
            solve_time_seconds=0.0,
            solver_name="deterministic earliest-available baseline",
        ),
        "cost_optimized": _scenario_result(
            name="DepotFlux cost-optimized EV + BESS",
            depot_power_kw=depot_power_kw,
            bess_power_kw=cost_bess["net_power_kw"],
            buy_prices=buy_prices,
            sell_prices=sell_prices,
            interval_hours=interval_hours,
            aggregator_margin_cad=float(depot_result["aggregator_revenue"]),
            battery_throughput_kwh=cost_bess["throughput_kwh"],
            solve_time_seconds=depot_solve_seconds + cost_bess["solve_time_seconds"],
            solver_name=f"{depot_result['solver_name']} + {cost_bess['solver_name']}",
            bess_dispatch=cost_bess,
        ),
        "grid_constrained": _scenario_result(
            name="DepotFlux EV + grid-constrained BESS",
            depot_power_kw=depot_power_kw,
            bess_power_kw=constrained_bess["net_power_kw"],
            buy_prices=buy_prices,
            sell_prices=sell_prices,
            interval_hours=interval_hours,
            aggregator_margin_cad=float(depot_result["aggregator_revenue"]),
            battery_throughput_kwh=constrained_bess["throughput_kwh"],
            solve_time_seconds=depot_solve_seconds
            + constrained_bess["solve_time_seconds"],
            solver_name=(
                f"{depot_result['solver_name']} + {constrained_bess['solver_name']}"
            ),
            bess_dispatch=constrained_bess,
        ),
    }
    base_case = run_power_flow(0.0, 0.0)
    evidence = {
        "experiment_id": "gridtwin-cigre-mv-depot-a-8-v1",
        "experiment_version": "1.0",
        "synthetic_only": True,
        "direct_asset_control": False,
        "input": {
            "reference": descriptor.reference,
            "sha256": descriptor.sha256,
            "fleet_size": descriptor.fleet_size,
            "interval_minutes": descriptor.interval_minutes,
            "horizon_intervals": descriptor.horizon_intervals,
            "provenance": descriptor.provenance,
        },
        "software": {
            "pandapower": version("pandapower"),
            "pymodbus": version("pymodbus"),
            "optimizer": "retained DepotFlux Pyomo MILP",
        },
        "grid": {
            "benchmark": FeederConfiguration().benchmark,
            "source": "pandapower open CIGRE MV benchmark, with_der=False",
            "base_load_scale": FeederConfiguration().base_load_scale,
            "depot_bus": "Bus 11",
            "bess_bus": "Bus 11",
            "hosting_limit_kw": envelope_kw,
            "limits": GridLimits().__dict__,
            "base_case": base_case,
        },
        "bess": BessConfiguration().__dict__,
        "scenarios": scenarios,
        "comparison": _comparison(scenarios),
        "optimizer_log_tail": optimizer_log.getvalue().splitlines()[-5:],
    }
    if include_security:
        evidence["security"] = run_security_experiment(evidence)
    evidence["total_runtime_seconds"] = time.perf_counter() - total_started
    return evidence


def _scenario_result(
    *,
    name: str,
    depot_power_kw: list[float],
    bess_power_kw: list[float],
    buy_prices: list[float],
    sell_prices: list[float],
    interval_hours: float,
    aggregator_margin_cad: float,
    battery_throughput_kwh: float,
    solve_time_seconds: float,
    solver_name: str,
    bess_dispatch: dict | None = None,
) -> dict:
    site_power_kw = [a + b for a, b in zip(depot_power_kw, bess_power_kw)]
    import_kwh = [max(0.0, value) * interval_hours for value in site_power_kw]
    export_kwh = [max(0.0, -value) * interval_hours for value in site_power_kw]
    energy_cost = sum(
        buy_prices[index] * import_kwh[index]
        - sell_prices[index] * export_kwh[index]
        for index in range(len(site_power_kw))
    )
    export_revenue = sum(
        sell_prices[index] * export_kwh[index]
        for index in range(len(site_power_kw))
    )
    flow = evaluate_schedule(
        depot_power_kw,
        bess_power_kw,
        interval_hours=interval_hours,
    )
    result = {
        "name": name,
        "depot_power_kw": depot_power_kw,
        "bess_power_kw": bess_power_kw,
        "site_power_kw": site_power_kw,
        "metrics": {
            "energy_cost_cad": energy_cost,
            "export_revenue_cad": export_revenue,
            "aggregator_margin_cad": aggregator_margin_cad,
            "grid_import_kwh": sum(import_kwh),
            "grid_export_kwh": sum(export_kwh),
            "peak_site_demand_kw": max(site_power_kw),
            "peak_feeder_demand_kw": max(
                row["feeder_import_kw"] for row in flow["intervals"]
            ),
            "battery_throughput_kwh": battery_throughput_kwh,
            "solve_time_seconds": solve_time_seconds,
            "solver_name": solver_name,
            "unserved_energy_kwh": 0.0,
        },
        "power_flow": flow,
    }
    if bess_dispatch is not None:
        result["bess_dispatch"] = bess_dispatch
    return result


def _comparison(scenarios: dict[str, dict]) -> dict:
    uncontrolled = scenarios["uncontrolled"]
    cost = scenarios["cost_optimized"]
    constrained = scenarios["grid_constrained"]
    return {
        "cost_optimized_vs_uncontrolled": _delta(cost, uncontrolled),
        "grid_constrained_vs_cost_optimized": _delta(constrained, cost),
        "minimum_evidence_gate": {
            "three_scenarios_completed": True,
            "cost_optimizer_reused": True,
            "grid_constrained_schedule_has_no_violations": (
                constrained["power_flow"]["voltage_violation_intervals"] == 0
                and constrained["power_flow"]["thermal_violation_intervals"] == 0
            ),
        },
    }


def _delta(candidate: dict, baseline: dict) -> dict:
    candidate_metrics = candidate["metrics"]
    baseline_metrics = baseline["metrics"]
    return {
        "energy_cost_cad": candidate_metrics["energy_cost_cad"]
        - baseline_metrics["energy_cost_cad"],
        "peak_site_demand_kw": candidate_metrics["peak_site_demand_kw"]
        - baseline_metrics["peak_site_demand_kw"],
        "energy_losses_kwh": candidate["power_flow"]["energy_losses_kwh"]
        - baseline["power_flow"]["energy_losses_kwh"],
        "voltage_violation_intervals": candidate["power_flow"][
            "voltage_violation_intervals"
        ]
        - baseline["power_flow"]["voltage_violation_intervals"],
        "thermal_violation_intervals": candidate["power_flow"][
            "thermal_violation_intervals"
        ]
        - baseline["power_flow"]["thermal_violation_intervals"],
    }
