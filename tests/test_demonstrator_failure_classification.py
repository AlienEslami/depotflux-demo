from __future__ import annotations

import pytest

from aggregator_demo import optimizer_service


def test_day_ahead_timeout_is_not_reported_as_infeasible(monkeypatch):
    monkeypatch.setattr(optimizer_service.day_ahead_core, "build_dataframes", lambda _data: {})
    monkeypatch.setattr(
        optimizer_service.day_ahead_core,
        "extract_scalars",
        lambda *_args, **_kwargs: {},
    )

    def timeout(_scalars, *, time_limit_seconds):
        assert time_limit_seconds == 0.001
        raise TimeoutError("solver reached its limit")

    monkeypatch.setattr(optimizer_service.day_ahead_core, "solvePTO", timeout)
    with pytest.raises(optimizer_service.OptimizationTimeoutError):
        optimizer_service.optimize_day_ahead(
            {},
            optimization_mode="selfish",
            v2g_enabled=True,
            solver_time_limit_seconds=0.001,
        )


def test_real_time_timeout_without_an_incumbent_is_classified_separately(monkeypatch):
    monkeypatch.setattr(optimizer_service.real_time_core, "build_dataframes", lambda _data: {})
    monkeypatch.setattr(
        optimizer_service.real_time_core,
        "build_rt_context",
        lambda *_args, **_kwargs: {"buses": [], "prices": {"spot": [0.1]}},
    )

    def timeout(_context, *, time_limit_seconds):
        assert time_limit_seconds == 0.001
        return None, {"solver_status": "aborted/maxTimeLimit"}

    monkeypatch.setattr(optimizer_service.real_time_core, "solve_rt_rescheduling", timeout)
    with pytest.raises(optimizer_service.OptimizationTimeoutError):
        optimizer_service.optimize_real_time(
            {"prices": [0.1]},
            structured_facts={
                "effective_from_timestep": 1,
                "solver_time_limit_seconds": 0.001,
            },
            baseline_result={},
            baseline_result_sha256="a" * 64,
            baseline_run_id="baseline",
            notice_id="notice",
            optimization_mode="selfish",
            v2g_enabled=True,
        )
