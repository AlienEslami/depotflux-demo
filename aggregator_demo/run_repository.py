from __future__ import annotations

import hashlib
import json
from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .contracts import RunCreateRequest, RunResponse, RunResultResponse, RunStatus
from .database import RunRow, utc_now


class RunNotFoundError(LookupError):
    pass


class RunConflictError(RuntimeError):
    pass


ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {
        RunStatus.RUNNING,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    },
    RunStatus.RUNNING: {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.INFEASIBLE,
        RunStatus.TIMED_OUT,
        RunStatus.CANCEL_REQUESTED,
        RunStatus.DEGRADED,
    },
    RunStatus.CANCEL_REQUESTED: {
        RunStatus.CANCELLED,
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
    },
    RunStatus.SUCCEEDED: set(),
    RunStatus.FAILED: set(),
    RunStatus.INFEASIBLE: set(),
    RunStatus.TIMED_OUT: set(),
    RunStatus.CANCELLED: set(),
    RunStatus.DEGRADED: set(),
}


def request_fingerprint(request: RunCreateRequest) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _as_utc(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def run_response(row: RunRow) -> RunResponse:
    return RunResponse(
        id=UUID(row.id),
        status=RunStatus(row.status),
        run_type=row.run_type,
        optimization_mode=row.optimization_mode,
        input_reference=row.input_reference,
        input_sha256=row.input_sha256,
        v2g_enabled=row.v2g_enabled,
        agent_backend=row.agent_backend,
        scenario_ids=list(row.scenario_ids),
        requested_by=row.requested_by,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        started_at=_as_utc(row.started_at),
        completed_at=_as_utc(row.completed_at),
        failure_code=row.failure_code,
        failure_message=row.failure_message,
    )


class RunRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        request: RunCreateRequest,
        *,
        requested_by: str,
        idempotency_key: str | None,
    ) -> tuple[RunResponse, bool]:
        fingerprint = request_fingerprint(request)
        if idempotency_key:
            existing = self._find_by_idempotency_key(idempotency_key)
            if existing is not None:
                return self._resolve_idempotent(existing, fingerprint), False

        now = utc_now()
        row = RunRow(
            id=str(uuid4()),
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            status=RunStatus.QUEUED.value,
            run_type=request.run_type.value,
            optimization_mode=request.optimization_mode.value,
            input_reference=request.input_reference,
            input_sha256=request.input_sha256,
            v2g_enabled=request.v2g_enabled,
            agent_backend=request.agent_backend.value,
            scenario_ids=list(request.scenario_ids),
            requested_by=requested_by,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            if not idempotency_key:
                raise
            existing = self._find_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            return self._resolve_idempotent(existing, fingerprint), False
        return run_response(row), True

    def get(self, run_id: UUID) -> RunResponse:
        return run_response(self._get_row(run_id))

    def list(self, *, limit: int, offset: int) -> list[RunResponse]:
        rows = self.session.scalars(
            select(RunRow)
            .order_by(RunRow.created_at.desc(), RunRow.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [run_response(row) for row in rows]

    def result(self, run_id: UUID) -> RunResultResponse:
        row = self._get_row(run_id)
        status = RunStatus(row.status)
        if not status.is_terminal:
            raise RunConflictError(f"run {run_id} has not reached a terminal state")
        return RunResultResponse(
            run_id=UUID(row.id),
            status=status,
            solver_name=row.solver_name,
            result_sha256=row.result_sha256,
            result=row.result_payload,
            failure_code=row.failure_code,
            failure_message=row.failure_message,
        )

    def claim_next(self, *, worker_id: str) -> RunResponse | None:
        """Atomically claim the oldest queued run for one durable worker."""
        for _ in range(10):
            run_id = self.session.scalar(
                select(RunRow.id)
                .where(RunRow.status == RunStatus.QUEUED.value)
                .order_by(RunRow.created_at.asc(), RunRow.id.asc())
                .limit(1)
            )
            if run_id is None:
                return None
            now = utc_now()
            claimed = self.session.execute(
                update(RunRow)
                .where(
                    RunRow.id == run_id,
                    RunRow.status == RunStatus.QUEUED.value,
                )
                .values(
                    status=RunStatus.RUNNING.value,
                    worker_id=worker_id,
                    started_at=now,
                    updated_at=now,
                )
            )
            self.session.commit()
            if claimed.rowcount == 1:
                return run_response(self._get_row(UUID(run_id)))
            self.session.expire_all()
        return None

    def complete(self, run_id: UUID, result: dict) -> RunResultResponse:
        canonical_result = json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        row = self._get_row(run_id)
        current = RunStatus(row.status)
        if current not in {RunStatus.RUNNING, RunStatus.CANCEL_REQUESTED}:
            raise RunConflictError(
                f"run {run_id} cannot complete from {current.value}"
            )
        row.result_payload = result
        row.result_sha256 = hashlib.sha256(canonical_result).hexdigest()
        row.solver_name = result.get("solver_name")
        row.status = RunStatus.SUCCEEDED.value
        row.updated_at = utc_now()
        row.completed_at = row.updated_at
        row.failure_code = None
        row.failure_message = None
        self.session.commit()
        return self.result(run_id)

    def fail(
        self,
        run_id: UUID,
        *,
        status: RunStatus,
        failure_code: str,
        failure_message: str,
    ) -> RunResultResponse:
        if status not in {
            RunStatus.FAILED,
            RunStatus.INFEASIBLE,
            RunStatus.TIMED_OUT,
            RunStatus.DEGRADED,
        }:
            raise ValueError(f"{status.value} is not a worker failure status")
        self.transition(
            run_id,
            status,
            failure_code=failure_code,
            failure_message=failure_message,
        )
        return self.result(run_id)

    def request_cancellation(self, run_id: UUID) -> RunResponse:
        row = self._get_row(run_id)
        current = RunStatus(row.status)
        if current == RunStatus.CANCELLED or current == RunStatus.CANCEL_REQUESTED:
            return run_response(row)
        target = (
            RunStatus.CANCELLED
            if current == RunStatus.QUEUED
            else RunStatus.CANCEL_REQUESTED
        )
        return self.transition(run_id, target)

    def transition(
        self,
        run_id: UUID,
        target: RunStatus,
        *,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> RunResponse:
        row = self._get_row(run_id)
        current = RunStatus(row.status)
        if current == target:
            return run_response(row)
        if target not in ALLOWED_TRANSITIONS[current]:
            raise RunConflictError(
                f"run {run_id} cannot transition from {current.value} to {target.value}"
            )

        now = utc_now()
        row.status = target.value
        row.updated_at = now
        if target == RunStatus.RUNNING and row.started_at is None:
            row.started_at = now
        if target.is_terminal:
            row.completed_at = now
        row.failure_code = failure_code
        row.failure_message = failure_message
        self.session.commit()
        return run_response(row)

    def _get_row(self, run_id: UUID) -> RunRow:
        row = self.session.get(RunRow, str(run_id))
        if row is None:
            raise RunNotFoundError(f"run {run_id} was not found")
        return row

    def _find_by_idempotency_key(self, key: str) -> RunRow | None:
        return self.session.scalar(
            select(RunRow).where(RunRow.idempotency_key == key)
        )

    @staticmethod
    def _resolve_idempotent(row: RunRow, fingerprint: str) -> RunResponse:
        if row.request_fingerprint != fingerprint:
            raise RunConflictError(
                "idempotency key was already used for a different run request"
            )
        return run_response(row)
