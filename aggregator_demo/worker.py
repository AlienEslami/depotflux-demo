from __future__ import annotations

import argparse
import os
import socket
import time
from pathlib import Path

from .contracts import AgentBackend, OptimizationMode, RunStatus, RunType
from .database import create_database_engine, create_session_factory, database_url_from_environment
from .input_registry import DemoInputError, DemoInputRegistry
from .optimizer_service import (
    OptimizationInfeasibleError,
    OptimizationResultError,
    optimize_day_ahead,
)
from .run_repository import RunRepository


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def execute_one(
    *,
    database_url: str | None = None,
    input_root: Path | None = None,
    worker_id: str | None = None,
) -> bool:
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    registry = DemoInputRegistry(input_root)
    try:
        with session_factory() as session:
            repository = RunRepository(session)
            claimed = repository.claim_next(worker_id=worker_id or worker_identity())
            if claimed is None:
                return False
            try:
                if claimed.run_type != RunType.DAY_AHEAD:
                    raise NotImplementedError(
                        "real-time runs are not connected to the demonstrator worker yet"
                    )
                if claimed.optimization_mode != OptimizationMode.SELFISH:
                    raise NotImplementedError(
                        "only selfish day-ahead optimization is connected to the worker"
                    )
                if claimed.agent_backend != AgentBackend.RULE:
                    raise NotImplementedError(
                        "only the deterministic rule backend is connected to the worker"
                    )
                if claimed.scenario_ids not in ([], ["nominal"]):
                    raise NotImplementedError(
                        "only the nominal day-ahead scenario is connected to the worker"
                    )
                input_data = registry.load(
                    claimed.input_reference,
                    claimed.input_sha256,
                )
                result = optimize_day_ahead(
                    input_data,
                    optimization_mode=claimed.optimization_mode.value,
                    v2g_enabled=claimed.v2g_enabled,
                )
                repository.complete(claimed.id, result)
            except DemoInputError as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.FAILED,
                    failure_code=exc.code,
                    failure_message=str(exc),
                )
            except OptimizationInfeasibleError as exc:
                repository.fail(
                    claimed.id,
                    status=RunStatus.INFEASIBLE,
                    failure_code="optimization_infeasible",
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
            return True
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the durable optimization worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued run.")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--input-root", type=Path, default=None)
    args = parser.parse_args(argv)
    database_url = database_url_from_environment()
    while True:
        processed = execute_one(
            database_url=database_url,
            input_root=args.input_root,
        )
        if args.once:
            return 0
        if not processed:
            time.sleep(max(0.1, args.poll_interval))


if __name__ == "__main__":
    raise SystemExit(main())
