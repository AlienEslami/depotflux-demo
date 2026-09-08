from __future__ import annotations

import argparse
import logging
import os
import socket
import time
from pathlib import Path

from .contracts import AgentBackend, OptimizationMode, RunStatus, RunType
from .database import create_database_engine, create_session_factory, database_url_from_environment
from .input_registry import DemoInputError, DemoInputRegistry
from .notice_repository import NoticeNotFoundError, NoticeRepository
from .optimizer_service import (
    OptimizationInfeasibleError,
    OptimizationResultError,
    OptimizationTimeoutError,
    optimize_day_ahead,
    optimize_real_time,
)
from .run_repository import RunRepository
from .observability import configure_logging


logger = logging.getLogger("depotflux.worker")


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def execute_one(
    *,
    database_url: str | None = None,
    input_root: Path | None = None,
    worker_id: str | None = None,
    stale_after_seconds: float | None = None,
) -> bool:
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    registry = DemoInputRegistry(input_root)
    try:
        with session_factory() as session:
            repository = RunRepository(session)
            if stale_after_seconds is None:
                stale_after_seconds = float(
                    os.environ.get("DEMO_STALE_RUN_SECONDS", "1800")
                )
            repository.recover_stale(stale_after_seconds=stale_after_seconds)
            active_worker_id = worker_id or worker_identity()
            claimed = repository.claim_next(worker_id=active_worker_id)
            if claimed is None:
                return False
            logger.info(
                "optimization run claimed",
                extra={"run_id": str(claimed.id), "worker_id": active_worker_id},
            )
            try:
                if claimed.optimization_mode != OptimizationMode.SELFISH:
                    raise NotImplementedError(
                        "only selfish optimization is connected to the worker"
                    )
                if claimed.agent_backend != AgentBackend.RULE:
                    raise NotImplementedError(
                        "only the deterministic rule backend is connected to the worker"
                    )
                input_data = registry.load(
                    claimed.input_reference,
                    claimed.input_sha256,
                )
                if claimed.run_type == RunType.DAY_AHEAD:
                    if claimed.scenario_ids in ([], ["nominal"]):
                        solver_time_limit_seconds = None
                    elif claimed.scenario_ids == ["failure_drill:infeasible"]:
                        for bus in input_data.get("buses", []):
                            bus["initial_soc"] = 0.0
                        solver_time_limit_seconds = None
                    elif claimed.scenario_ids == ["failure_drill:solver_timeout"]:
                        solver_time_limit_seconds = 0.001
                    else:
                        raise NotImplementedError(
                            "the requested day-ahead scenario is not connected to the worker"
                        )
                    result = optimize_day_ahead(
                        input_data,
                        optimization_mode=claimed.optimization_mode.value,
                        v2g_enabled=claimed.v2g_enabled,
                        solver_time_limit_seconds=solver_time_limit_seconds,
                    )
                elif claimed.run_type == RunType.REAL_TIME:
                    notice = NoticeRepository(session).get_by_candidate(claimed.id)
                    baseline = repository.result(notice.baseline_run_id)
                    if baseline.result is None or baseline.result_sha256 is None:
                        raise OptimizationResultError(
                            "approved baseline result is unavailable"
                        )
                    result = optimize_real_time(
                        input_data,
                        structured_facts=notice.structured_facts,
                        baseline_result=baseline.result,
                        baseline_result_sha256=baseline.result_sha256,
                        baseline_run_id=str(notice.baseline_run_id),
                        notice_id=str(notice.id),
                        optimization_mode=claimed.optimization_mode.value,
                        v2g_enabled=claimed.v2g_enabled,
                    )
                else:
                    raise NotImplementedError(
                        f"run type {claimed.run_type.value} is unsupported"
                    )
                if result.get("validation", {}).get("passed") is True:
                    repository.complete(claimed.id, result)
                else:
                    repository.complete_degraded(
                        claimed.id,
                        result,
                        failure_code="deterministic_validation_failed",
                        failure_message=(
                            "The solver returned a candidate, but deterministic "
                            "operational validation did not pass."
                        ),
                    )
            except DemoInputError as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.FAILED,
                    failure_code=exc.code,
                    failure_message=str(exc),
                )
            except NoticeNotFoundError as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.FAILED,
                    failure_code="notice_not_found",
                    failure_message=str(exc),
                )
            except OptimizationInfeasibleError as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.INFEASIBLE,
                    failure_code="optimization_infeasible",
                    failure_message=str(exc),
                )
            except OptimizationTimeoutError as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.TIMED_OUT,
                    failure_code="solver_time_limit",
                    failure_message=str(exc),
                )
            except OptimizationResultError as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.FAILED,
                    failure_code="invalid_optimization_result",
                    failure_message=str(exc),
                )
            except NotImplementedError as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.FAILED,
                    failure_code="unsupported_run_configuration",
                    failure_message=str(exc),
                )
            except Exception as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.FAILED,
                    failure_code="unexpected_worker_error",
                    failure_message=f"{type(exc).__name__}: {exc}",
                )
            completed = repository.get(claimed.id)
            logger.info(
                "optimization run finished",
                extra={
                    "run_id": str(completed.id),
                    "worker_id": active_worker_id,
                    "run_status": completed.status.value,
                    "failure_code": completed.failure_code,
                },
            )
            return True
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    configure_logging(os.environ.get("DEMO_LOG_LEVEL", "INFO").upper())
    parser = argparse.ArgumentParser(description="Run the durable optimization worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued run.")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--input-root", type=Path, default=None)
    parser.add_argument("--stale-after", type=float, default=None)
    args = parser.parse_args(argv)
    database_url = database_url_from_environment()
    while True:
        processed = execute_one(
            database_url=database_url,
            input_root=args.input_root,
            stale_after_seconds=args.stale_after,
        )
        if args.once:
            return 0
        if not processed:
            time.sleep(max(0.1, args.poll_interval))


if __name__ == "__main__":
    raise SystemExit(main())
