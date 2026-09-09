from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Sequence

import pyomo.environ as pyo


@dataclass(frozen=True)
class BessConfiguration:
    capacity_kwh: float = 500.0
    maximum_charge_kw: float = 250.0
    maximum_discharge_kw: float = 250.0
    minimum_soc: float = 0.10
    maximum_soc: float = 0.90
    initial_soc: float = 0.50
    final_soc: float = 0.50
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95


class GridDispatchInfeasibleError(RuntimeError):
    pass


def uncontrolled_charging_schedule(
    required_energy_kwh: float,
    horizon_steps: int,
    *,
    interval_hours: float,
    site_capacity_kw: float,
) -> list[float]:
    """Earliest-available aggregate charging with no price/grid response."""
    if required_energy_kwh < 0 or horizon_steps < 1:
        raise ValueError("uncontrolled charging inputs are invalid")
    schedule = [0.0] * horizon_steps
    remaining = float(required_energy_kwh)
    for index in range(horizon_steps):
        energy = min(remaining, site_capacity_kw * interval_hours)
        schedule[index] = energy / interval_hours
        remaining -= energy
        if remaining <= 1e-7:
            break
    if remaining > 1e-6:
        raise GridDispatchInfeasibleError(
            "required energy exceeds the uncontrolled charging horizon"
        )
    return schedule


def optimize_bess_dispatch(
    depot_power_kw: Sequence[float],
    buy_price_per_kwh: Sequence[float],
    sell_price_per_kwh: Sequence[float],
    *,
    interval_hours: float,
    configuration: BessConfiguration = BessConfiguration(),
    maximum_site_import_kw: float | Sequence[float] | None = None,
) -> dict:
    """Optimize a BESS around the retained DepotFlux EV schedule."""
    horizon = len(depot_power_kw)
    if not horizon or len(buy_price_per_kwh) != horizon or len(sell_price_per_kwh) != horizon:
        raise ValueError("power and price series must share a non-empty horizon")
    if maximum_site_import_kw is None:
        import_limits = None
    elif isinstance(maximum_site_import_kw, (int, float)):
        import_limits = [float(maximum_site_import_kw)] * horizon
    else:
        import_limits = [float(value) for value in maximum_site_import_kw]
        if len(import_limits) != horizon:
            raise ValueError("grid envelope must cover the complete horizon")

    cfg = configuration
    model = pyo.ConcreteModel()
    model.T = pyo.RangeSet(1, horizon)
    model.E = pyo.RangeSet(0, horizon)
    model.charge = pyo.Var(model.T, bounds=(0.0, cfg.maximum_charge_kw))
    model.discharge = pyo.Var(model.T, bounds=(0.0, cfg.maximum_discharge_kw))
    model.energy = pyo.Var(
        model.E,
        bounds=(cfg.minimum_soc * cfg.capacity_kwh, cfg.maximum_soc * cfg.capacity_kwh),
    )
    model.grid_import = pyo.Var(model.T, within=pyo.NonNegativeReals)
    model.grid_export = pyo.Var(model.T, within=pyo.NonNegativeReals)
    model.energy[0].fix(cfg.initial_soc * cfg.capacity_kwh)
    for step in model.T:
        model.add_component(
            f"energy_balance_{step}",
            pyo.Constraint(
                expr=model.energy[step]
                == model.energy[step - 1]
                + cfg.charge_efficiency * model.charge[step] * interval_hours
                - model.discharge[step]
                * interval_hours
                / cfg.discharge_efficiency
            ),
        )
        model.add_component(
            f"site_balance_{step}",
            pyo.Constraint(
                expr=model.grid_import[step] - model.grid_export[step]
                == float(depot_power_kw[step - 1])
                + model.charge[step]
                - model.discharge[step]
            ),
        )
        if import_limits is not None:
            model.add_component(
                f"grid_envelope_{step}",
                pyo.Constraint(expr=model.grid_import[step] <= import_limits[step - 1]),
            )
    model.final_soc = pyo.Constraint(
        expr=model.energy[horizon] == cfg.final_soc * cfg.capacity_kwh
    )
    model.objective = pyo.Objective(
        expr=sum(
            (
                float(buy_price_per_kwh[step - 1]) * model.grid_import[step]
                - float(sell_price_per_kwh[step - 1]) * model.grid_export[step]
            )
            * interval_hours
            for step in model.T
        ),
        sense=pyo.minimize,
    )

    solver_name, result, solve_seconds = _solve(model)
    termination = str(result.solver.termination_condition).lower()
    if termination not in {"optimal", "locallyoptimal", "feasible"}:
        raise GridDispatchInfeasibleError(
            f"BESS dispatch did not produce a feasible schedule: {termination}"
        )
    charge = [float(pyo.value(model.charge[step])) for step in model.T]
    discharge = [float(pyo.value(model.discharge[step])) for step in model.T]
    energy = [float(pyo.value(model.energy[step])) for step in model.E]
    site_power = [
        float(depot_power_kw[index]) + charge[index] - discharge[index]
        for index in range(horizon)
    ]
    return {
        "configuration": asdict(cfg),
        "solver_name": solver_name,
        "solver_termination": termination,
        "solve_time_seconds": solve_seconds,
        "charge_power_kw": charge,
        "discharge_power_kw": discharge,
        "net_power_kw": [a - b for a, b in zip(charge, discharge)],
        "energy_kwh": energy,
        "site_power_kw": site_power,
        "throughput_kwh": sum(
            (a + b) * interval_hours for a, b in zip(charge, discharge)
        ),
    }


def _solve(model) -> tuple[str, object, float]:
    configured = os.environ.get("GRIDTWIN_SOLVER_ORDER", "appsi_highs,highs")
    errors: list[str] = []
    for name in [item.strip() for item in configured.split(",") if item.strip()]:
        solver = pyo.SolverFactory(name)
        try:
            if not solver.available(exception_flag=False):
                errors.append(f"{name}: unavailable")
                continue
            started = time.perf_counter()
            result = solver.solve(model, tee=False)
            return name, result, time.perf_counter() - started
        except Exception as exc:  # pragma: no cover - environment-specific fallback
            errors.append(f"{name}: {exc}")
    raise GridDispatchInfeasibleError(
        "no configured BESS solver was usable: " + "; ".join(errors)
    )
