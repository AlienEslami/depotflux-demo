from __future__ import annotations

from scripts.run_gridtwin_evidence import _measure_api


def test_api_benchmark_authenticates_when_api_key_mode_is_enabled(monkeypatch):
    monkeypatch.setenv("DEMO_AUTH_MODE", "api_key")
    for role in ("OPERATOR", "APPROVER", "AUDITOR", "ADMIN"):
        monkeypatch.setenv(
            f"DEMO_{role}_API_KEY",
            f"gridtwin-test-{role.lower()}-credential",
        )

    result = _measure_api(sample_count=3)

    assert result["sample_count"] == 3
    assert result["p50_ms"] >= 0
    assert result["p95_ms"] >= result["p50_ms"]
