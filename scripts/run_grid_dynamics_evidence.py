from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["svg.hashsalt"] = "gridtwin-dynamics-v1"
matplotlib.rcParams["svg.fonttype"] = "none"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aggregator_demo.gridtwin.dynamics import (
    DynamicParameters,
    SCENARIOS,
    analytical_two_bus_voltage_pu,
    parameter_table,
    run_step_sensitivity,
    schedule_feedback,
    solve_operating_point,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the GridTwin averaged electromagnetic-transient evidence study"
    )
    parser.add_argument(
        "--schedule-evidence",
        type=Path,
        default=Path("evidence/gridtwin/results.json"),
        help="Existing GridTwin schedule evidence JSON",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("evidence/grid-dynamics")
    )
    args = parser.parse_args()
    schedule = json.loads(args.schedule_evidence.read_text(encoding="utf-8"))
    constrained = schedule["scenarios"]["grid_constrained"]
    depot_power = [float(value) for value in constrained["depot_power_kw"]]
    bess_power = [float(value) for value in constrained["bess_power_kw"]]
    site_power = [depot + bess for depot, bess in zip(depot_power, bess_power)]
    selected_index = max(range(len(site_power)), key=site_power.__getitem__)
    selected_depot_kw = depot_power[selected_index]
    selected_bess_power_kw = bess_power[selected_index]
    inverter_injection_kw = max(0.0, -selected_bess_power_kw)
    parameters = DynamicParameters()

    sensitivity, simulations = run_step_sensitivity(
        charger_power_kw=selected_depot_kw,
        inverter_injection_kw=inverter_injection_kw,
        parameters=parameters,
    )
    selected_step = sensitivity["selected_step_s"]
    scenario_results = {
        scenario.key: simulations[f"{scenario.key}:{selected_step}"].summary()
        for scenario in SCENARIOS
    }

    analytical_voltage = analytical_two_bus_voltage_pu(
        selected_depot_kw,
        inverter_injection_kw,
        parameters=parameters,
    )
    numerical_no_shunt = solve_operating_point(
        selected_depot_kw,
        inverter_injection_kw,
        parameters=parameters,
        include_pcc_capacitance=False,
    )
    numerical_voltage = (
        abs(numerical_no_shunt["voltage_phase_rms"])
        / parameters.phase_voltage_rms_v
    )
    analytical_error = abs(analytical_voltage - numerical_voltage)
    operating_point = solve_operating_point(
        selected_depot_kw,
        inverter_injection_kw,
        parameters=parameters,
        include_pcc_capacitance=True,
    )
    feedback = schedule_feedback(
        depot_power,
        bess_power,
        schedule_limit_kw=float(schedule["grid"]["hosting_limit_kw"]),
        parameters=parameters,
    )
    all_scenarios_passed = all(
        row["criteria"]["passed"] for row in scenario_results.values()
    )
    evidence = {
        "experiment_id": "gridtwin-averaged-emt-depot-a-8-v1",
        "experiment_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "synthetic_only": True,
        "direct_asset_control": False,
        "model_classification": (
            "balanced positive-sequence synchronous-dq averaged electromagnetic-transient model"
        ),
        "explicit_non_claims": [
            "not a switching-level converter model",
            "not a protection-coordination or insulation-coordination study",
            "not field-calibrated and not validated against measurements",
            "not MATLAB/Simulink, PSCAD, EMTP, PowerFactory, PLECS, RTDS, Typhoon HIL or OPAL-RT evidence",
        ],
        "software": {
            "python": sys.version.split()[0],
            "numpy": version("numpy"),
            "matplotlib": version("matplotlib"),
            "integrator": "project-owned deterministic fixed-step classical RK4",
        },
        "schedule_source": {
            "path": args.schedule_evidence.as_posix(),
            "experiment_id": schedule["experiment_id"],
            "input_reference": schedule["input"]["reference"],
            "input_sha256": schedule["input"]["sha256"],
            "selected_interval_index_zero_based": selected_index,
            "depot_power_kw": selected_depot_kw,
            "bess_schedule_power_kw": selected_bess_power_kw,
            "bess_inverter_injection_kw": inverter_injection_kw,
            "site_power_kw": site_power[selected_index],
        },
        "parameters": parameter_table(parameters),
        "validation": {
            "analytical_baseline": {
                "description": "closed-form high-voltage receiving-end solution for the same two-bus constant-P/Q operating point with the declared PCC shunt omitted",
                "analytical_voltage_pu": analytical_voltage,
                "numerical_fixed_point_voltage_pu": numerical_voltage,
                "absolute_error_pu": analytical_error,
                "tolerance_pu": 1.0e-8,
                "passed": analytical_error <= 1.0e-8,
            },
            "initialized_model_residual": {
                "phasor_equation_residual_v": operating_point["residual_v"],
                "tolerance_v": 1.0e-6,
                "passed": operating_point["residual_v"] <= 1.0e-6,
            },
            "step_sensitivity": sensitivity,
        },
        "scenarios": scenario_results,
        "schedule_feedback": feedback,
        "minimum_evidence_gate": {
            "four_required_scenarios_completed": len(scenario_results) == 4,
            "all_scenario_response_criteria_passed": all_scenarios_passed,
            "analytical_baseline_passed": analytical_error <= 1.0e-8,
            "selected_step_and_finer_comparisons_passed": sensitivity["passed"],
            "schedule_feedback_emitted": feedback["workflow_action"]
            in {"accept_schedule", "request_reschedule"},
        },
    }
    evidence["minimum_evidence_gate"]["passed"] = all(
        evidence["minimum_evidence_gate"].values()
    )

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(
        json.dumps(evidence, indent=2, allow_nan=False, default=_json_scalar) + "\n",
        encoding="utf-8",
    )
    (args.output / "technical-report.md").write_text(
        _markdown_report(evidence), encoding="utf-8"
    )
    _write_response_plot(evidence, args.output / "dynamic-responses.svg")
    _write_sensitivity_plot(evidence, args.output / "step-sensitivity.svg")
    print(
        json.dumps(
            {
                "experiment_id": evidence["experiment_id"],
                "output": str(args.output.resolve()),
                "selected_schedule_interval": selected_index,
                "gate_passed": evidence["minimum_evidence_gate"]["passed"],
                "workflow_action": feedback["workflow_action"],
            },
            indent=2,
        )
    )
    return 0 if evidence["minimum_evidence_gate"]["passed"] else 1


def _json_scalar(value):
    """Convert NumPy scalar results without weakening the no-NaN evidence gate."""
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"unsupported evidence value: {type(value).__name__}")


def _markdown_report(result: dict) -> str:
    source = result["schedule_source"]
    validation = result["validation"]
    feedback = result["schedule_feedback"]
    lines = [
        "# GridTwin averaged electromagnetic-transient study",
        "",
        f"Generated: `{result['generated_at']}`",
        f"Experiment: `{result['experiment_id']}`",
        "",
        "> Synthetic, software-only portfolio evidence. No physical asset was controlled. This is a balanced averaged-value study, not switching-level EMT, field validation, licensed-tool experience, protection coordination or a production grid model.",
        "",
        "## Purpose and integration",
        "",
        "The study consumes the existing GridTwin grid-constrained EV/BESS trajectory. It selects the highest-import interval, maps the charger demand and scheduled BESS support into a transparent source–feeder–PCC model, runs four short electrical disturbances, and returns a deterministic accept/reschedule message to the existing monitoring and remaining-horizon workflow.",
        "",
        "## Schedule-derived operating point",
        "",
        "| Input | Value |",
        "|---|---:|",
        f"| Source experiment | `{source['experiment_id']}` |",
        f"| Selected interval (zero-based) | {source['selected_interval_index_zero_based']} |",
        f"| Aggregate charger demand | {source['depot_power_kw']:.3f} kW |",
        f"| BESS schedule sign (positive = charge) | {source['bess_schedule_power_kw']:.3f} kW |",
        f"| BESS inverter injection | {source['bess_inverter_injection_kw']:.3f} kW |",
        f"| Net scheduled site demand | {source['site_power_kw']:.3f} kW |",
        "",
        "## Electrical model and assumptions",
        "",
        "The fixed-step RK4 solver integrates eight synchronous-dq states: feeder d/q current, PCC d/q voltage, charger d/q current and BESS-inverter d/q current. The source and transformer/feeder are a Thevenin voltage behind series R–L. The PCC includes aggregate cable/filter capacitance, a small shunt conductance and an idealized voltage-dependent surge clamp. Charger and inverter currents track constant-P/Q references with explicit time constants and ratings. A balanced fault is a temporary equal per-phase shunt resistance.",
        "",
        "| Parameter | Value |",
        "|---|---:|",
    ]
    for name, value in result["parameters"].items():
        lines.append(f"| `{name}` | {value:.9g} |" if isinstance(value, float) else f"| `{name}` | {value} |")
    lines.extend(
        [
            "",
            "## Scenario results and pass/fail criteria",
            "",
            "![Four dynamic scenario responses](dynamic-responses.svg)",
            "",
            "| Scenario | V min/max (pu) | I max (pu) | f min/max (Hz) | P peak (kW) | Abs Q peak (kvar) | Recovery (ms) | Result |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for scenario in result["scenarios"].values():
        metrics = scenario["metrics"]
        recovery_ms = (
            "n/a" if metrics["recovery_time_s"] is None else f"{1_000 * metrics['recovery_time_s']:.3f}"
        )
        lines.append(
            f"| {scenario['scenario']['title']} | {metrics['minimum_voltage_pu']:.4f} / {metrics['maximum_voltage_pu']:.4f} | "
            f"{metrics['maximum_feeder_current_pu']:.4f} | {metrics['minimum_frequency_hz']:.3f} / {metrics['maximum_frequency_hz']:.3f} | "
            f"{metrics['peak_active_power_kw']:.1f} | {metrics['peak_absolute_reactive_power_kvar']:.1f} | {recovery_ms} | "
            f"{'PASS' if scenario['criteria']['passed'] else 'FAIL'} |"
        )
    for scenario in result["scenarios"].values():
        lines.extend(["", f"Criteria for **{scenario['scenario']['title']}**:", ""])
        for check in scenario["criteria"]["checks"]:
            lines.append(
                f"- {'PASS' if check['passed'] else 'FAIL'} — {check['name']}: `{check['value']}`; limit `{check['limit']}`."
            )
        lines.extend(["", "Recorded violation durations:", ""])
        for name, value in scenario["violations"].items():
            lines.append(f"- `{name}`: `{value:.6f}` s.")
    analytical = validation["analytical_baseline"]
    lines.extend(
        [
            "",
            "## Validation and solver-step sensitivity",
            "",
            f"The independent quadratic two-bus solution gives `{analytical['analytical_voltage_pu']:.12f} pu`; the iterative phasor initializer gives `{analytical['numerical_fixed_point_voltage_pu']:.12f} pu`. Absolute error is `{analytical['absolute_error_pu']:.3e} pu` against `{analytical['tolerance_pu']:.1e} pu`: **{'PASS' if analytical['passed'] else 'FAIL'}**.",
            "",
            "![Solver-step sensitivity](step-sensitivity.svg)",
            "",
            "The reference uses the same equations at 6.25 µs. A response comparison uses the 99th-percentile absolute waveform error so one sample at an ideal discontinuity does not dominate; voltage/current extrema and recovery time are checked separately. The selected 25 µs step and every tested finer step must pass. The deliberately retained 50 µs run exposes coarse-step sensitivity and is not used for reported scenario metrics.",
            "",
            "| Scenario | Step (µs) | Waveform check | Extrema check |",
            "|---|---:|---|---|",
        ]
    )
    for name, scenario in validation["step_sensitivity"]["scenarios"].items():
        for row in scenario["runs"]:
            waveform_pass = all(item["passed"] for item in row["comparisons"].values())
            extrema_pass = all(item["passed"] for item in row["extrema_comparisons"].values())
            lines.append(
                f"| `{name}` | {row['candidate_step_s'] * 1e6:.2f} | {'PASS' if waveform_pass else 'FAIL'} | {'PASS' if extrema_pass else 'FAIL'} |"
            )
    lines.extend(
        [
            "",
            "## Monitoring and rescheduling feedback",
            "",
            f"The loss-of-BESS-support screen returned **`{feedback['workflow_action']}`**. Settled contingency voltage was `{feedback['contingency_final_voltage_pu']:.6f} pu` versus the documented planning threshold `{feedback['contingency_minimum_voltage_requirement_pu']:.3f} pu`. Recommended maximum depot import is `{feedback['recommended_maximum_depot_import_kw']}` kW. The output includes `replanning_structured_facts` with per-charger deratings in the same contract consumed by the existing remaining-horizon optimizer. This is a decision-support bound; it is not dispatched to equipment.",
            "",
            "## Limitations",
            "",
            "- Balanced positive-sequence representation; unbalance, harmonics, switching ripple, saturation and detailed converter controls are excluded.",
            "- Frequency is a one-cycle PCC-voltage angle estimate against a fixed 60 Hz source; this model has no synchronous-machine swing dynamics.",
            "- Fault and surge-clamp elements are deliberately simple equivalents. Fault current is not suitable for relay settings or equipment-duty decisions.",
            "- Parameters are declared engineering assumptions, not utility, OEM or field measurements. Results establish only deterministic software-model behavior.",
            "- The finer-step run checks numerical convergence of the same equations, not correctness against a commercial EMT package or physical system.",
            "",
            "## Reproduce",
            "",
            "From the `GridTwin-Ops` directory with the pinned Python environment installed:",
            "",
            "```powershell",
            "python scripts/run_grid_dynamics_evidence.py",
            "python -m pytest -q tests/test_gridtwin_dynamics.py tests/test_grid_dynamics_evidence_script.py",
            "```",
            "",
            "Outputs are `results.json`, this report, `dynamic-responses.svg` and `step-sensitivity.svg` under `evidence/grid-dynamics/`.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_response_plot(result: dict, output: Path) -> None:
    figure, axes = plt.subplots(4, 2, figsize=(12, 12), sharex="col")
    for row_index, scenario in enumerate(result["scenarios"].values()):
        trace = scenario["trace"]
        time = trace["time_s"]
        left = axes[row_index, 0]
        right = axes[row_index, 1]
        left.plot(time, trace["voltage_pu"], label="PCC voltage (pu)", color="#2563eb")
        left.plot(time, trace["feeder_current_pu"], label="Feeder current (pu)", color="#dc2626", alpha=0.8)
        left.axvline(scenario["scenario"]["event_start_s"], color="#475569", linestyle="--", linewidth=0.8)
        if scenario["scenario"]["event_clear_s"] is not None:
            left.axvline(scenario["scenario"]["event_clear_s"], color="#475569", linestyle=":", linewidth=0.8)
        left.set_ylabel(scenario["scenario"]["key"].replace("_", " "))
        left.grid(alpha=0.2)
        right.plot(time, trace["active_power_kw"], label="P (kW)", color="#059669")
        right.plot(time, trace["reactive_power_kvar"], label="Q (kvar)", color="#7c3aed", alpha=0.85)
        right.grid(alpha=0.2)
    axes[0, 0].legend(loc="best", fontsize=8)
    axes[0, 1].legend(loc="best", fontsize=8)
    axes[-1, 0].set_xlabel("Time (s)")
    axes[-1, 1].set_xlabel("Time (s)")
    figure.suptitle("Schedule-derived GridTwin averaged dynamic responses")
    figure.tight_layout()
    figure.savefig(output, format="svg", metadata={"Date": None})
    plt.close(figure)
    _normalize_generated_text(output)


def _write_sensitivity_plot(result: dict, output: Path) -> None:
    figure, axis = plt.subplots(figsize=(9, 5))
    for scenario_name, scenario in result["validation"]["step_sensitivity"]["scenarios"].items():
        steps = [row["candidate_step_s"] * 1e6 for row in scenario["runs"]]
        errors = [
            row["comparisons"]["voltage_pu"]["waveform_99th_percentile_absolute_error"]
            for row in scenario["runs"]
        ]
        axis.plot(steps, errors, marker="o", label=scenario_name.replace("_", " "))
    axis.axhline(0.005, color="#dc2626", linestyle="--", label="voltage tolerance")
    axis.set_xlabel("Candidate RK4 step (µs)")
    axis.set_ylabel("Voltage waveform 99th-percentile absolute error (pu)")
    axis.set_title("Fixed-step sensitivity against 6.25 µs reference")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(output, format="svg", metadata={"Date": None})
    plt.close(figure)
    _normalize_generated_text(output)


def _normalize_generated_text(path: Path) -> None:
    """Keep generated text artifacts deterministic and diff-check clean."""
    content = path.read_text(encoding="utf-8")
    path.write_text(
        "\n".join(line.rstrip() for line in content.splitlines()) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
