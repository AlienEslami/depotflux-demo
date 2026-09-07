from __future__ import annotations

import copy
import math

import pyomo.environ as pyo

import app as day_ahead_core


class OptimizationInfeasibleError(RuntimeError):
    pass


class OptimizationResultError(RuntimeError):
    pass


def optimize_day_ahead(
    input_data: dict,
    *,
    optimization_mode: str,
    v2g_enabled: bool,
) -> dict:
    """Run the existing mathematical core without legacy job-file side effects."""
    optimizer_input = copy.deepcopy(input_data)
    optimizer_input["v2g_enabled"] = v2g_enabled
    data = day_ahead_core.build_dataframes(optimizer_input)
    scalars = day_ahead_core.extract_scalars(
        data,
        price_guidance={},
        optimization_mode="day_ahead",
        current_timestep=1,
    )
    model = day_ahead_core.solvePTO(scalars)
    if model is None:
        raise OptimizationInfeasibleError("day-ahead optimization is infeasible")

    timestep_count = scalars["T_steps"]
    buy = [
        float(pyo.value(model.w_buy[timestep]))
        for timestep in range(1, timestep_count + 1)
    ]
    sell = [
        float(pyo.value(model.w_sell[timestep]))
        for timestep in range(1, timestep_count + 1)
    ]
    energy = [
        [
            float(pyo.value(model.e[bus, timestep]))
            for timestep in range(1, timestep_count + 1)
        ]
        for bus in range(1, scalars["k_count"] + 1)
    ]

    total_buy_cost = sum(
        scalars["S_buy"][index] * buy[index]
        for index in range(timestep_count)
    )
    total_sell_revenue = sum(
        scalars["S_sell"][index] * sell[index]
        for index in range(timestep_count)
    )
    aggregator_buy_margin = sum(
        (scalars["S_buy"][index] - scalars["P"][index]) * buy[index]
        for index in range(timestep_count)
    )
    aggregator_sell_margin = sum(
        (scalars["P"][index] - scalars["S_sell"][index]) * sell[index]
        for index in range(timestep_count)
    )

    result = {
        "result_version": "v1",
        "run_type": "day_ahead",
        "optimization_mode": optimization_mode,
        "optimized_steps": timestep_count,
        "v2g_enabled": bool(scalars.get("v2g_enabled", True)),
        "solver_name": getattr(model, "_solver_name", None),
        "solver_fallback_errors": getattr(model, "_solver_fallback_errors", []),
        "buy_multipliers": scalars["buy_multipliers"],
        "sell_multipliers": scalars["sell_multipliers"],
        "avg_grid_price": scalars["avg_P"],
        "avg_buy_price": scalars["avg_S_buy"],
        "avg_sell_price": scalars["avg_S_sell"],
        "pto_daily_cost": total_buy_cost - total_sell_revenue,
        "aggregator_revenue": aggregator_buy_margin + aggregator_sell_margin,
        "aggregator_buy_margin": aggregator_buy_margin,
        "aggregator_sell_margin": aggregator_sell_margin,
        "total_buy_cost": total_buy_cost,
        "total_sell_revenue": total_sell_revenue,
        "total_kwh_sold": sum(sell),
        "total_kwh_bought": sum(buy),
        "w_buy": buy,
        "w_sell": sell,
        "energy": energy,
    }
    _validate_result(result, bus_count=scalars["k_count"])
    result["validation"] = {
        "passed": True,
        "checks": [
            "finite_numeric_outputs",
            "complete_site_power_horizon",
            "complete_bus_energy_horizon",
            "nonnegative_energy_and_site_exchange",
        ],
    }
    return result


def _validate_result(result: dict, *, bus_count: int) -> None:
    steps = int(result["optimized_steps"])
    if len(result["w_buy"]) != steps or len(result["w_sell"]) != steps:
        raise OptimizationResultError("site power series does not cover the horizon")
    if len(result["energy"]) != bus_count or any(
        len(trajectory) != steps for trajectory in result["energy"]
    ):
        raise OptimizationResultError("bus energy series does not cover the horizon")
    numeric_values = [
        result["pto_daily_cost"],
        result["aggregator_revenue"],
        *result["w_buy"],
        *result["w_sell"],
        *(value for trajectory in result["energy"] for value in trajectory),
    ]
    if any(not math.isfinite(float(value)) for value in numeric_values):
        raise OptimizationResultError("optimization result contains non-finite values")
    if any(value < -1e-7 for value in [
        *result["w_buy"],
        *result["w_sell"],
        *(value for trajectory in result["energy"] for value in trajectory),
    ]):
        raise OptimizationResultError("optimization result contains negative physical values")
