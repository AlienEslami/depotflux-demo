from __future__ import annotations

import copy
import math

import pyomo.environ as pyo

import app as day_ahead_core
import app_rt as real_time_core


class OptimizationInfeasibleError(RuntimeError):
    pass


class OptimizationResultError(RuntimeError):
    pass


class OptimizationTimeoutError(RuntimeError):
    pass


def _solver_status_is_timeout(status: object) -> bool:
    normalized = str(status or "").lower().replace("_", "").replace(" ", "")
    return "timelimit" in normalized or "maxtime" in normalized


def optimize_day_ahead(
    input_data: dict,
    *,
    optimization_mode: str,
    v2g_enabled: bool,
    solver_time_limit_seconds: float | None = None,
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
    try:
        model = day_ahead_core.solvePTO(
            scalars,
            time_limit_seconds=solver_time_limit_seconds,
        )
    except TimeoutError as exc:
        raise OptimizationTimeoutError(str(exc)) from exc
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


def optimize_real_time(
    input_data: dict,
    *,
    structured_facts: dict,
    baseline_result: dict,
    baseline_result_sha256: str,
    baseline_run_id: str,
    notice_id: str,
    optimization_mode: str,
    v2g_enabled: bool,
) -> dict:
    """Re-optimize the executable horizon after a frozen operational notice."""
    optimizer_input = copy.deepcopy(input_data)
    optimizer_input["v2g_enabled"] = v2g_enabled
    horizon_steps = len(optimizer_input.get("prices") or [])
    if horizon_steps < 1:
        raise OptimizationResultError("real-time input has no price horizon")

    current_timestep = int(structured_facts.get("effective_from_timestep", 1))
    baseline_energy = baseline_result.get("energy") or []
    state_index = max(0, current_timestep - 2)
    for state in optimizer_input.get("realtime_state", []):
        bus_index = int(state.get("bus_id", 0)) - 1
        if 0 <= bus_index < len(baseline_energy):
            trajectory = baseline_energy[bus_index]
            if state_index < len(trajectory):
                state["current_energy_kwh"] = float(trajectory[state_index])
                state["current_timestep"] = current_timestep

    for derating in structured_facts.get("charger_deratings", []):
        charger_id = int(derating["charger_id"])
        start = max(1, int(derating["start_timestep"]))
        end = min(horizon_steps, int(derating["end_timestep"]))
        derated_kw = max(0.0, float(derating["to_kw"]))
        for charger in optimizer_input.get("chargers", []):
            if int(charger.get("charger_id", 0)) != charger_id:
                continue
            normal_kw = float(
                charger.get("max_power_kw", charger.get("charger_kw", 0.0))
            )
            schedule = [normal_kw] * horizon_steps
            for index in range(start - 1, end):
                schedule[index] = derated_kw
            charger["power_schedule_kw"] = schedule

    disturbances = [
        {
            "disturbance_type": "delay",
            "bus_id": int(item["bus_id"]),
            "delay_minutes": int(item["delay_minutes"]),
        }
        for item in structured_facts.get("late_returns", [])
    ]
    data = real_time_core.build_dataframes(optimizer_input)
    context = real_time_core.build_rt_context(
        data,
        payload_price_guidance={},
        current_timestep=current_timestep,
        disturbances=disturbances,
    )
    model, solve_meta = real_time_core.solve_rt_rescheduling(
        context,
        time_limit_seconds=structured_facts.get("solver_time_limit_seconds"),
    )
    if model is None:
        reason = solve_meta.get("solver_status") or "unknown solver status"
        if _solver_status_is_timeout(reason):
            raise OptimizationTimeoutError(
                f"remaining-horizon solver reached its time limit: {reason}"
            )
        raise OptimizationInfeasibleError(
            f"remaining-horizon optimization is infeasible: {reason}"
        )

    series = real_time_core.extract_time_series_results(model, context)
    step_count = len(context["prices"]["spot"])
    buy = series["w_buy"]
    sell = series["w_sell"]
    total_buy_cost = sum(
        context["prices"]["buy"][index] * buy[index]
        for index in range(step_count)
    )
    total_sell_revenue = sum(
        context["prices"]["sell"][index] * sell[index]
        for index in range(step_count)
    )
    aggregator_buy_margin = sum(
        (context["prices"]["buy"][index] - context["prices"]["spot"][index])
        * buy[index]
        for index in range(step_count)
    )
    aggregator_sell_margin = sum(
        (context["prices"]["spot"][index] - context["prices"]["sell"][index])
        * sell[index]
        for index in range(step_count)
    )
    service_unmet_duration = sum(
        covered is False
        for coverage in series["trip_coverage_by_timestep"].values()
        for covered in coverage.values()
    )
    soc_violation_count = sum(
        float(shortfall) > 1e-6
        for bus_shortfall in series["soc_shortfall"]
        for shortfall in bus_shortfall
    )

    result = {
        "result_version": "v1",
        "run_type": "real_time",
        "optimization_mode": optimization_mode,
        "current_timestep": context["current_timestep"],
        "optimized_steps": step_count,
        "v2g_enabled": context["v2g_enabled"],
        "solver_name": solve_meta.get("solver_name"),
        "solver_status": solve_meta.get("solver_status"),
        "solver_fallback_errors": solve_meta.get("solver_fallback_errors", []),
        "optimization_strategy": solve_meta.get("optimization_strategy"),
        "avg_grid_price": sum(context["prices"]["spot"]) / step_count,
        "avg_buy_price": sum(context["prices"]["buy"]) / step_count,
        "avg_sell_price": sum(context["prices"]["sell"]) / step_count,
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
        "energy": series["energy"],
        "soc_shortfall": series["soc_shortfall"],
        "trip_assignment_by_timestep": series["trip_assignment_by_timestep"],
        "trip_coverage_by_timestep": series["trip_coverage_by_timestep"],
        "temporarily_unserved_trip_ids": series["temporarily_unserved_trip_ids"],
        "service_interruption_events": series["service_interruption_events"],
        "service_restoration_events": series["service_restoration_events"],
        "reassignment_mapping": series["reassignment_mapping"],
        "service_unmet_count": len(series["temporarily_unserved_trip_ids"]),
        "service_unmet_duration": int(service_unmet_duration),
        "soc_violation_count": int(soc_violation_count),
        "remaining_horizon_start": context["current_timestep"],
        "remaining_horizon_end": context["current_timestep"] + step_count - 1,
        "notice": {
            "notice_id": notice_id,
            "structured_facts": structured_facts,
        },
    }
    _validate_result(result, bus_count=len(context["buses"]))
    solver_completed_within_limit = not _solver_status_is_timeout(
        result["solver_status"]
    )
    validation_passed = (
        result["service_unmet_count"] == 0
        and result["soc_violation_count"] == 0
        and solver_completed_within_limit
    )
    result["validation"] = {
        "passed": validation_passed,
        "checks": [
            "finite_numeric_outputs",
            "complete_site_power_horizon",
            "complete_bus_energy_horizon",
            "nonnegative_energy_and_site_exchange",
            "no_unserved_service",
            "no_soc_shortfall",
            "solver_completed_within_limit",
        ],
        "failed_checks": [
            name
            for name, passed in (
                ("no_unserved_service", result["service_unmet_count"] == 0),
                ("no_soc_shortfall", result["soc_violation_count"] == 0),
                ("solver_completed_within_limit", solver_completed_within_limit),
            )
            if not passed
        ],
    }
    result["comparison"] = _compare_with_baseline(
        baseline_result,
        candidate=result,
        prices=context["prices"],
        baseline_result_sha256=baseline_result_sha256,
        baseline_run_id=baseline_run_id,
    )
    return result


def _compare_with_baseline(
    baseline: dict,
    *,
    candidate: dict,
    prices: dict,
    baseline_result_sha256: str,
    baseline_run_id: str,
) -> dict:
    start = int(candidate["remaining_horizon_start"]) - 1
    steps = int(candidate["optimized_steps"])
    baseline_buy = list(baseline.get("w_buy") or [])[start : start + steps]
    baseline_sell = list(baseline.get("w_sell") or [])[start : start + steps]
    if len(baseline_buy) != steps or len(baseline_sell) != steps:
        raise OptimizationResultError(
            "approved baseline does not cover the replanning horizon"
        )
    candidate_buy = candidate["w_buy"]
    candidate_sell = candidate["w_sell"]
    baseline_cost = sum(
        prices["buy"][index] * baseline_buy[index]
        - prices["sell"][index] * baseline_sell[index]
        for index in range(steps)
    )
    candidate_cost = float(candidate["pto_daily_cost"])
    baseline_net = [
        baseline_buy[index] - baseline_sell[index] for index in range(steps)
    ]
    candidate_net = [
        candidate_buy[index] - candidate_sell[index] for index in range(steps)
    ]
    baseline_energy = [
        list(trajectory)[start : start + steps]
        for trajectory in baseline.get("energy") or []
    ]
    candidate_energy = [list(trajectory) for trajectory in candidate.get("energy") or []]
    energy_changes_by_step = [
        any(
            bus_index >= len(baseline_energy)
            or step_index >= len(baseline_energy[bus_index])
            or abs(
                float(candidate_energy[bus_index][step_index])
                - float(baseline_energy[bus_index][step_index])
            )
            > 1e-6
            for bus_index in range(len(candidate_energy))
        )
        for step_index in range(steps)
    ]
    power_changes_by_step = [
        abs(candidate_net[index] - baseline_net[index]) > 1e-6
        for index in range(steps)
    ]
    return {
        "baseline_run_id": baseline_run_id,
        "baseline_result_sha256": baseline_result_sha256,
        "horizon_start": start + 1,
        "horizon_steps": steps,
        "changed_intervals": sum(
            power_changes_by_step[index] or energy_changes_by_step[index]
            for index in range(steps)
        ),
        "site_power_changed_intervals": sum(power_changes_by_step),
        "fleet_energy_changed_intervals": sum(energy_changes_by_step),
        "baseline": {
            "remaining_cost": baseline_cost,
            "grid_purchase_kwh": sum(baseline_buy),
            "v2g_export_kwh": sum(baseline_sell),
            "peak_import_kwh": max(baseline_buy, default=0.0),
        },
        "candidate": {
            "remaining_cost": candidate_cost,
            "grid_purchase_kwh": sum(candidate_buy),
            "v2g_export_kwh": sum(candidate_sell),
            "peak_import_kwh": max(candidate_buy, default=0.0),
        },
        "delta": {
            "remaining_cost": candidate_cost - baseline_cost,
            "grid_purchase_kwh": sum(candidate_buy) - sum(baseline_buy),
            "v2g_export_kwh": sum(candidate_sell) - sum(baseline_sell),
            "peak_import_kwh": max(candidate_buy, default=0.0)
            - max(baseline_buy, default=0.0),
        },
    }


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
