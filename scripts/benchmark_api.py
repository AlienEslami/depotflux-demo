from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx


def read_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_timings(
    durations_seconds: list[float], *, successful: int, total_seconds: float
) -> dict[str, float | int]:
    total = len(durations_seconds)
    return {
        "requests": total,
        "successful_requests": successful,
        "failed_requests": total - successful,
        "error_rate": round((total - successful) / total, 6) if total else 0.0,
        "throughput_requests_per_second": round(total / total_seconds, 3)
        if total_seconds > 0
        else 0.0,
        "latency_ms_min": round(min(durations_seconds) * 1000, 3)
        if durations_seconds
        else 0.0,
        "latency_ms_mean": round(statistics.fmean(durations_seconds) * 1000, 3)
        if durations_seconds
        else 0.0,
        "latency_ms_p50": round(percentile(durations_seconds, 0.50) * 1000, 3),
        "latency_ms_p95": round(percentile(durations_seconds, 0.95) * 1000, 3),
        "latency_ms_p99": round(percentile(durations_seconds, 0.99) * 1000, 3),
        "latency_ms_max": round(max(durations_seconds) * 1000, 3)
        if durations_seconds
        else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure a bounded read-only DepotFlux API workload."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--endpoint", default="/api/v1/runs?limit=25&offset=0")
    parser.add_argument("--env-file", type=Path, default=Path(".demo/ot-lab.env"))
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    parser.add_argument("--output", type=Path, default=Path(".demo/evidence/api-benchmark.json"))
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests and concurrency must be positive")
    if args.concurrency > args.requests:
        parser.error("concurrency may not exceed requests")

    environment = read_environment(args.env_file)
    access_key = environment.get("DEMO_AUDITOR_API_KEY")
    if not access_key:
        raise ValueError("DEMO_AUDITOR_API_KEY is missing from the environment file")
    headers = {"Authorization": f"Bearer {access_key}"}
    url = f"{args.base_url.rstrip('/')}/{args.endpoint.lstrip('/')}"
    durations: list[float] = []
    statuses: list[int] = []

    with httpx.Client(timeout=args.timeout, headers=headers) as client:
        warmup = client.get(url)
        warmup.raise_for_status()

        def request_once() -> tuple[float, int]:
            started = time.perf_counter()
            try:
                response = client.get(url)
                return time.perf_counter() - started, response.status_code
            except httpx.HTTPError:
                return time.perf_counter() - started, 0

        workload_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [executor.submit(request_once) for _ in range(args.requests)]
            for future in as_completed(futures):
                duration, status_code = future.result()
                durations.append(duration)
                statuses.append(status_code)
        total_seconds = time.perf_counter() - workload_started

    successful = sum(200 <= status < 300 for status in statuses)
    summary = summarize_timings(
        durations, successful=successful, total_seconds=total_seconds
    )
    passed = (
        float(summary["error_rate"]) <= args.max_error_rate
        and float(summary["latency_ms_p95"]) <= args.max_p95_ms
    )
    payload = {
        "schema_version": "depotflux-api-benchmark-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": {"base_url": args.base_url, "endpoint": args.endpoint},
        "workload": {
            "requests": args.requests,
            "concurrency": args.concurrency,
            "read_only": True,
        },
        "thresholds": {
            "max_error_rate": args.max_error_rate,
            "max_p95_ms": args.max_p95_ms,
        },
        "result": summary,
        "passed": passed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
