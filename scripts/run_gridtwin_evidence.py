from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aggregator_demo.gridtwin.service import run_evidence_sprint


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local GridTwin evidence sprint")
    parser.add_argument("--output", type=Path, default=Path("evidence/gridtwin"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    result = run_evidence_sprint()
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["api_benchmark"] = _measure_api()
    (args.output / "results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "results.md").write_text(_markdown(result), encoding="utf-8")
    (args.output / "schedule-comparison.svg").write_text(
        _schedule_svg(result), encoding="utf-8"
    )
    with (args.output / "audit.jsonl").open("w", encoding="utf-8") as stream:
        for record in result["security"]["audit_records"]:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps({
        "experiment_id": result["experiment_id"],
        "output": str(args.output.resolve()),
        "runtime_seconds": result["total_runtime_seconds"],
        "gate_passed": result["comparison"]["minimum_evidence_gate"],
    }, indent=2))
    return 0


def _markdown(result: dict) -> str:
    lines = [
        "# GridTwin measured results",
        "",
        f"Generated: `{result['generated_at']}`",
        "",
        "Synthetic, software-only evidence; no physical asset was controlled.",
        "",
        "| Scenario | Cost (CAD) | Export revenue (CAD) | Peak site (kW) | Losses (kWh) | Voltage violation intervals | Thermal violation intervals | BESS throughput (kWh) | Solve time (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in ("uncontrolled", "cost_optimized", "grid_constrained"):
        scenario = result["scenarios"][key]
        metrics = scenario["metrics"]
        flow = scenario["power_flow"]
        lines.append(
            f"| {scenario['name']} | {metrics['energy_cost_cad']:.3f} | "
            f"{metrics['export_revenue_cad']:.3f} | {metrics['peak_site_demand_kw']:.1f} | "
            f"{flow['energy_losses_kwh']:.3f} | {flow['voltage_violation_intervals']} | "
            f"{flow['thermal_violation_intervals']} | {metrics['battery_throughput_kwh']:.3f} | "
            f"{metrics['solve_time_seconds']:.3f} |"
        )
    security = result["security"]
    metrics = security["detection_metrics"]
    lines.extend(
        [
            "",
            "## Security evidence",
            "",
            f"- False-data injection detected: `{security['false_data_injection']['detected']}`.",
            f"- Unauthorized/unsafe set-point denied by gateway policy: `{security['unauthorized_setpoint']['denied']}` (`{security['unauthorized_setpoint']['gateway_policy_code']}`).",
            f"- Observed Modbus write/read attempts after denial: `{security['unauthorized_setpoint']['modbus_write_attempts']}` / `{security['unauthorized_setpoint']['modbus_read_attempts']}`; frame transmitted: `{security['unauthorized_setpoint']['frame_transmitted']}`.",
            f"- Precision/recall/F1: `{metrics['precision']:.3f}` / `{metrics['recall']:.3f}` / `{metrics['f1']:.3f}` on {metrics['sample_count']} deterministic paired samples.",
            f"- False-positive rate: `{metrics['false_positive_rate']:.3f}`.",
            f"- Mean/max synchronous detection delay: `{metrics['mean_detection_delay_ms']:.3f} ms` / `{metrics['maximum_detection_delay_ms']:.3f} ms`.",
            f"- Remaining post-recovery violations: `{security['false_data_injection']['remaining_violations']}`.",
            f"- Recovery objective loss: `{security['objective_loss_cad']:.3f} CAD`.",
            f"- Audit hash chain valid: `{security['audit_chain_valid']}`.",
            f"- Local GridTwin metadata API p50/p95 ({result['api_benchmark']['sample_count']} requests): `{result['api_benchmark']['p50_ms']:.3f} ms` / `{result['api_benchmark']['p95_ms']:.3f} ms`.",
            "",
            "## Baseline and limitations",
            "",
            "The feeder is pandapower's open CIGRE MV benchmark with existing loads scaled to 0.55. The EV depot and 500 kWh / 250 kW BESS are connected at Bus 11. The BESS inverter follows a fixed 0.98 power factor. Results are deterministic fixtures, not utility measurements, field validation, or standards compliance evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _measure_api(sample_count: int = 30) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi.testclient import TestClient

    from aggregator_demo.app import create_app

    with tempfile.TemporaryDirectory(prefix="gridtwin-api-") as directory:
        database = Path(directory) / "benchmark.db"
        app = create_app(
            database_url=f"sqlite:///{database.as_posix()}",
            initialize_schema=True,
        )
        client = TestClient(app)
        headers = {}
        if operator_key := os.environ.get("DEMO_OPERATOR_API_KEY"):
            headers["Authorization"] = f"Bearer {operator_key}"
        durations: list[float] = []
        previous_logging_threshold = logging.root.manager.disable
        try:
            logging.disable(logging.CRITICAL)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                for _ in range(sample_count):
                    started = time.perf_counter()
                    response = client.get("/api/v1/gridtwin/meta", headers=headers)
                    durations.append((time.perf_counter() - started) * 1000.0)
                    if response.status_code != 200:
                        raise RuntimeError("GridTwin metadata benchmark request failed")
        finally:
            logging.disable(previous_logging_threshold)
        app.state.database_engine.dispose()
    ordered = sorted(durations)
    p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return {
        "endpoint": "GET /api/v1/gridtwin/meta (in-process TestClient)",
        "sample_count": sample_count,
        "p50_ms": median(ordered),
        "p95_ms": ordered[p95_index],
        "maximum_ms": max(ordered),
    }


def _schedule_svg(result: dict) -> str:
    width, height, pad = 960, 420, 55
    series = [
        ("Uncontrolled", result["scenarios"]["uncontrolled"]["site_power_kw"], "#d97706"),
        ("Cost optimized", result["scenarios"]["cost_optimized"]["site_power_kw"], "#2563eb"),
        ("Grid constrained", result["scenarios"]["grid_constrained"]["site_power_kw"], "#059669"),
    ]
    all_values = [value for _, values, _ in series for value in values]
    minimum, maximum = min(all_values + [0.0]), max(all_values)
    span = max(1.0, maximum - minimum)

    def point(index: int, value: float, count: int) -> str:
        x = pad + index * (width - 2 * pad) / max(1, count - 1)
        y = height - pad - (value - minimum) * (height - 2 * pad) / span
        return f"{x:.1f},{y:.1f}"

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="55" y="28" font-family="sans-serif" font-size="20" font-weight="600">GridTwin site-power schedules</text>',
        f'<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#94a3b8"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#94a3b8"/>',
    ]
    for label, values, color in series:
        points = " ".join(point(i, value, len(values)) for i, value in enumerate(values))
        elements.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{points}"/>'
        )
    envelope = result["grid"]["hosting_limit_kw"]
    envelope_y = height - pad - (envelope - minimum) * (height - 2 * pad) / span
    elements.extend(
        [
            f'<line x1="{pad}" y1="{envelope_y:.1f}" x2="{width-pad}" y2="{envelope_y:.1f}" stroke="#dc2626" stroke-dasharray="7 5"/>',
            f'<text x="{width-pad-190}" y="{envelope_y-7:.1f}" font-family="sans-serif" font-size="12" fill="#dc2626">AC power-flow envelope {envelope:.1f} kW</text>',
            f'<text x="{width/2-45}" y="{height-12}" font-family="sans-serif" font-size="13">30-minute interval</text>',
            f'<text transform="translate(16 {height/2+50}) rotate(-90)" font-family="sans-serif" font-size="13">Site power (kW)</text>',
        ]
    )
    for index, (label, _, color) in enumerate(series):
        x = pad + index * 190
        elements.append(f'<line x1="{x}" y1="{height-30}" x2="{x+24}" y2="{height-30}" stroke="{color}" stroke-width="3"/>')
        elements.append(f'<text x="{x+30}" y="{height-25}" font-family="sans-serif" font-size="12">{label}</text>')
    elements.append("</svg>")
    return "\n".join(elements) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
