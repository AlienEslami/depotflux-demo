from __future__ import annotations

import pytest

from scripts.benchmark_api import percentile, summarize_timings


def test_percentile_interpolates_ordered_values() -> None:
    values = [0.4, 0.1, 0.3, 0.2]
    assert percentile(values, 0.0) == 0.1
    assert percentile(values, 0.5) == pytest.approx(0.25)
    assert percentile(values, 1.0) == 0.4


def test_benchmark_summary_reports_latency_throughput_and_errors() -> None:
    summary = summarize_timings(
        [0.01, 0.02, 0.03, 0.04], successful=3, total_seconds=0.1
    )
    assert summary["requests"] == 4
    assert summary["failed_requests"] == 1
    assert summary["error_rate"] == 0.25
    assert summary["throughput_requests_per_second"] == 40.0
    assert summary["latency_ms_p50"] == 25.0
