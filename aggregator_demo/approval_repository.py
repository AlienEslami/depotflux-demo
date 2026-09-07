from __future__ import annotations

from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .contracts import (
    ApprovalCreateRequest,
    ApprovalDecision,
    ApprovalResponse,
    AuditEventResponse,
    RunStatus,
    RunTimelineResponse,
)
from .database import ApprovalRow, OperationalNoticeRow, RunRow, utc_now
from .run_repository import RunNotFoundError


class ApprovalNotFoundError(LookupError):
    pass


class ApprovalConflictError(RuntimeError):
    pass


def _as_utc(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def approval_response(row: ApprovalRow) -> ApprovalResponse:
    return ApprovalResponse(
        id=UUID(row.id),
        run_id=UUID(row.run_id),
        decision=ApprovalDecision(row.decision),
        decided_by=row.decided_by,
        result_sha256=row.result_sha256,
        note=row.note,
        created_at=_as_utc(row.created_at),
    )


class ApprovalRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, run_id: UUID) -> ApprovalResponse:
        row = self.session.scalar(
            select(ApprovalRow).where(ApprovalRow.run_id == str(run_id))
        )
        if row is None:
            raise ApprovalNotFoundError(f"run {run_id} has no operator decision")
        return approval_response(row)

    def create(
        self,
        run_id: UUID,
        request: ApprovalCreateRequest,
        *,
        decided_by: str,
    ) -> ApprovalResponse:
        run = self.session.get(RunRow, str(run_id))
        if run is None:
            raise RunNotFoundError(f"run {run_id} was not found")
        existing = self.session.scalar(
            select(ApprovalRow).where(ApprovalRow.run_id == str(run_id))
        )
        if existing is not None:
            return self._resolve_existing(existing, request, decided_by)
        if RunStatus(run.status) != RunStatus.SUCCEEDED:
            raise ApprovalConflictError("only a successful candidate can receive a decision")
        validation = (run.result_payload or {}).get("validation", {})
        if validation.get("passed") is not True or not run.result_sha256:
            raise ApprovalConflictError(
                "candidate has no passing deterministic validation result"
            )

        row = ApprovalRow(
            id=str(uuid4()),
            run_id=str(run_id),
            decision=request.decision.value,
            decided_by=decided_by,
            result_sha256=run.result_sha256,
            note=request.note,
            created_at=utc_now(),
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(ApprovalRow).where(ApprovalRow.run_id == str(run_id))
            )
            if existing is None:
                raise
            return self._resolve_existing(existing, request, decided_by)
        return approval_response(row)

    def timeline(self, run_id: UUID) -> RunTimelineResponse:
        run = self.session.get(RunRow, str(run_id))
        if run is None:
            raise RunNotFoundError(f"run {run_id} was not found")
        events = [
            AuditEventResponse(
                event_type="run_submitted",
                occurred_at=_as_utc(run.created_at),
                actor=run.requested_by,
                detail="Optimization run submitted to the durable queue.",
            )
        ]
        notice = self.session.scalar(
            select(OperationalNoticeRow).where(
                OperationalNoticeRow.candidate_run_id == str(run_id)
            )
        )
        if notice is not None:
            events.append(
                AuditEventResponse(
                    event_type="notice_received",
                    occurred_at=_as_utc(notice.created_at),
                    actor=notice.created_by,
                    detail=(
                        f"Simulator notice received: "
                        f"{notice.scenario.replace('_', ' ')}."
                    ),
                )
            )
        if run.started_at is not None:
            events.append(
                AuditEventResponse(
                    event_type="run_started",
                    occurred_at=_as_utc(run.started_at),
                    actor=run.worker_id or "optimization-worker",
                    detail="Worker claimed the run and started optimization.",
                )
            )
        if run.completed_at is not None:
            events.append(
                AuditEventResponse(
                    event_type="run_completed",
                    occurred_at=_as_utc(run.completed_at),
                    actor=run.worker_id or "optimization-worker",
                    detail=f"Run reached terminal status: {run.status}.",
                )
            )
        approval = self.session.scalar(
            select(ApprovalRow).where(ApprovalRow.run_id == str(run_id))
        )
        if approval is not None:
            events.append(
                AuditEventResponse(
                    event_type="decision_recorded",
                    occurred_at=_as_utc(approval.created_at),
                    actor=approval.decided_by,
                    detail=f"Candidate {approval.decision} by the operator.",
                )
            )
        events.sort(key=lambda event: event.occurred_at)
        return RunTimelineResponse(run_id=run_id, events=events)

    @staticmethod
    def _resolve_existing(
        row: ApprovalRow,
        request: ApprovalCreateRequest,
        decided_by: str,
    ) -> ApprovalResponse:
        if (
            row.decision != request.decision.value
            or row.note != request.note
            or row.decided_by != decided_by
        ):
            raise ApprovalConflictError(
                "this candidate already has a different immutable operator decision"
            )
        return approval_response(row)
