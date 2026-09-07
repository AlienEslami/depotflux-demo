from __future__ import annotations

from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .contracts import (
    AgentBackend,
    NoticeCreateRequest,
    NoticeResponse,
    NoticeScenario,
    RunCreateRequest,
    RunStatus,
    RunType,
)
from .database import ApprovalRow, OperationalNoticeRow, RunRow, utc_now
from .run_repository import RunNotFoundError, RunRepository


class NoticeNotFoundError(LookupError):
    pass


class NoticeConflictError(RuntimeError):
    pass


def _as_utc(value):
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def notice_response(row: OperationalNoticeRow) -> NoticeResponse:
    return NoticeResponse(
        id=UUID(row.id),
        baseline_run_id=UUID(row.baseline_run_id),
        candidate_run_id=UUID(row.candidate_run_id),
        scenario=row.scenario,
        source=row.source,
        raw_notice=row.raw_notice,
        structured_facts=dict(row.structured_facts),
        interpretation_backend=row.interpretation_backend,
        confidence=row.confidence,
        replan_recommended=row.replan_recommended,
        rationale=row.rationale,
        created_by=row.created_by,
        created_at=_as_utc(row.created_at),
    )


def _scenario_payload(scenario: NoticeScenario) -> dict:
    # Interval 14 has settled when the notice arrives; the candidate may only
    # change executable intervals beginning at 15.
    common = {"observed_at_timestep": 14, "effective_from_timestep": 15}
    if scenario == NoticeScenario.LATE_RETURN:
        return {
            "raw_notice": (
                "Operations update: bus 1 is returning 30 minutes late. "
                "Keep its evening service requirement protected."
            ),
            "structured_facts": {
                **common,
                "late_returns": [{"bus_id": 1, "delay_minutes": 30}],
                "charger_deratings": [],
            },
            "confidence": 0.99,
            "rationale": (
                "The late return changes when bus 1 is available for charging, so the "
                "remaining schedule should be checked against service and SOC constraints."
            ),
        }
    if scenario == NoticeScenario.CHARGER_DERATING:
        return {
            "raw_notice": (
                "Maintenance update: charger 1 is limited to 150 kW from timestep 15 "
                "through timestep 22. Normal capacity remains available afterward."
            ),
            "structured_facts": {
                **common,
                "late_returns": [],
                "charger_deratings": [
                    {
                        "charger_id": 1,
                        "from_kw": 200.0,
                        "to_kw": 150.0,
                        "start_timestep": 15,
                        "end_timestep": 22,
                    }
                ],
            },
            "confidence": 0.99,
            "rationale": (
                "Available charging power has changed during the operating horizon, so "
                "DepotFlux should calculate a revised feasible allocation."
            ),
        }
    return {
        "raw_notice": (
            "Combined operations update: bus 1 will return 30 minutes late. Charger 1 "
            "is limited to 150 kW from timestep 15 through timestep 22. Protect all "
            "remaining service requirements."
        ),
        "structured_facts": {
            **common,
            "late_returns": [{"bus_id": 1, "delay_minutes": 30}],
            "charger_deratings": [
                {
                    "charger_id": 1,
                    "from_kw": 200.0,
                    "to_kw": 150.0,
                    "start_timestep": 15,
                    "end_timestep": 22,
                }
            ],
        },
        "confidence": 0.99,
        "rationale": (
            "Vehicle availability and charger capacity changed together. A remaining-"
            "horizon optimization is required before the operator can adopt a revised plan."
        ),
    }


class NoticeRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_simulated(
        self,
        request: NoticeCreateRequest,
        *,
        created_by: str,
        idempotency_key: str | None,
    ) -> NoticeResponse:
        baseline = self.session.get(RunRow, str(request.baseline_run_id))
        if baseline is None:
            raise RunNotFoundError(
                f"baseline run {request.baseline_run_id} was not found"
            )
        approval = self.session.scalar(
            select(ApprovalRow).where(ApprovalRow.run_id == baseline.id)
        )
        if (
            baseline.status != RunStatus.SUCCEEDED.value
            or baseline.result_payload is None
            or baseline.result_sha256 is None
            or approval is None
            or approval.decision != "approved"
            or approval.result_sha256 != baseline.result_sha256
        ):
            raise NoticeConflictError(
                "a passing, approved candidate is required as the replanning baseline"
            )

        candidate_request = RunCreateRequest(
            run_type=RunType.REAL_TIME,
            optimization_mode=baseline.optimization_mode,
            input_reference=baseline.input_reference,
            input_sha256=baseline.input_sha256,
            v2g_enabled=baseline.v2g_enabled,
            agent_backend=AgentBackend.RULE,
            scenario_ids=[f"notice:{request.scenario.value}"],
        )
        candidate, created = RunRepository(self.session).create(
            candidate_request,
            requested_by=created_by,
            idempotency_key=(
                f"replan:{idempotency_key}" if idempotency_key is not None else None
            ),
        )
        existing = self.session.scalar(
            select(OperationalNoticeRow).where(
                OperationalNoticeRow.candidate_run_id == str(candidate.id)
            )
        )
        if existing is not None:
            if (
                existing.baseline_run_id != str(request.baseline_run_id)
                or existing.scenario != request.scenario.value
            ):
                raise NoticeConflictError(
                    "the idempotency key is already associated with another notice"
                )
            return notice_response(existing)
        if not created:
            raise NoticeConflictError(
                "the idempotent candidate exists without its operational notice"
            )

        payload = _scenario_payload(request.scenario)
        row = OperationalNoticeRow(
            id=str(uuid4()),
            baseline_run_id=baseline.id,
            candidate_run_id=str(candidate.id),
            scenario=request.scenario.value,
            source="simulator",
            raw_notice=payload["raw_notice"],
            structured_facts=payload["structured_facts"],
            interpretation_backend="rule",
            confidence=payload["confidence"],
            replan_recommended=True,
            rationale=payload["rationale"],
            created_by=created_by,
            created_at=utc_now(),
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise NoticeConflictError("the candidate already has a notice") from exc
        return notice_response(row)

    def get(self, notice_id: UUID) -> NoticeResponse:
        row = self.session.get(OperationalNoticeRow, str(notice_id))
        if row is None:
            raise NoticeNotFoundError(f"notice {notice_id} was not found")
        return notice_response(row)

    def get_by_candidate(self, run_id: UUID) -> NoticeResponse:
        row = self.session.scalar(
            select(OperationalNoticeRow).where(
                OperationalNoticeRow.candidate_run_id == str(run_id)
            )
        )
        if row is None:
            raise NoticeNotFoundError(
                f"run {run_id} is not linked to an operational notice"
            )
        return notice_response(row)

    def list(self, *, limit: int, offset: int) -> list[NoticeResponse]:
        rows = self.session.scalars(
            select(OperationalNoticeRow)
            .order_by(
                OperationalNoticeRow.created_at.desc(),
                OperationalNoticeRow.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return [notice_response(row) for row in rows]
