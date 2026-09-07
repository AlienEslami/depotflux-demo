from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .contracts import (
    ApprovalDecision,
    DispatchPolicyCheckResponse,
    OTDispatchAttemptResponse,
    RunStatus,
    SecurityEventResponse,
)
from .database import (
    ApprovalRow,
    OTDispatchAttemptRow,
    RunRow,
    SecurityEventRow,
    utc_now,
)
from .input_registry import DemoInputRegistry
from .ot_gateway import (
    GatewayDispatchRequest,
    GatewayPolicyError,
    GatewaySafeStateRequest,
    GatewayUnavailableError,
)
from .run_repository import RunNotFoundError


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def dispatch_attempt_response(row: OTDispatchAttemptRow) -> OTDispatchAttemptResponse:
    return OTDispatchAttemptResponse(
        id=UUID(row.id),
        run_id=UUID(row.run_id) if row.run_id else None,
        interval_index=row.interval_index,
        command_id=UUID(row.command_id),
        correlation_id=UUID(row.correlation_id),
        action=row.action,
        decision=row.decision,
        reason_code=row.reason_code,
        reason_message=row.reason_message,
        setpoint_kw=row.setpoint_kw,
        result_sha256=row.result_sha256,
        modbus_frame_hex=row.modbus_frame_hex,
        response_frame_hex=row.response_frame_hex,
        policy_checks=row.policy_checks,
        controller_response=row.controller_response,
        requested_by=row.requested_by,
        issued_at=_as_utc(row.issued_at),
        completed_at=_as_utc(row.completed_at),
        simulated_only=True,
    )


def security_event_response(row: SecurityEventRow) -> SecurityEventResponse:
    return SecurityEventResponse(
        id=UUID(row.id),
        event_type=row.event_type,
        severity=row.severity,
        correlation_id=UUID(row.correlation_id),
        run_id=UUID(row.run_id) if row.run_id else None,
        actor=row.actor,
        source_zone=row.source_zone,
        destination=row.destination,
        outcome=row.outcome,
        reason_code=row.reason_code,
        details=row.details,
        occurred_at=_as_utc(row.occurred_at),
        simulated_only=True,
    )


class DispatchRejectedError(RuntimeError):
    def __init__(self, attempt: OTDispatchAttemptResponse, status_code: int):
        super().__init__(attempt.reason_message)
        self.attempt = attempt
        self.status_code = status_code


class DispatchEvidenceRepository:
    POLICY_VERSION = "ot-dispatch-policy-v1"

    def __init__(self, session: Session, input_registry: DemoInputRegistry, gateway):
        self.session = session
        self.input_registry = input_registry
        self.gateway = gateway

    def dispatch(
        self,
        run_id: UUID,
        *,
        interval_index: int,
        requested_by: str,
        credential_accepted: bool,
        credential_configured: bool,
        command_id: UUID | None = None,
        issued_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> OTDispatchAttemptResponse:
        now = utc_now()
        issued = _as_utc(issued_at) if issued_at else now
        expires = _as_utc(expires_at) if expires_at else issued + timedelta(seconds=20)
        command = command_id or uuid4()
        correlation = uuid4()
        checks: list[DispatchPolicyCheckResponse] = []
        run = self.session.get(RunRow, str(run_id))
        if run is None:
            raise RunNotFoundError(f"run {run_id} was not found")

        self._require(
            credential_configured and credential_accepted,
            code="separate_control_credential",
            label="Separate control credential",
            passed_detail="A separately configured dispatch credential was accepted.",
            failed_detail=(
                "Dispatch is disabled because no separate credential is configured."
                if not credential_configured
                else "The separate dispatch credential was rejected."
            ),
            checks=checks,
            rejection=lambda code, detail: self._reject(
                run_id=run_id,
                interval_index=interval_index,
                command_id=command,
                correlation_id=correlation,
                requested_by=requested_by,
                issued_at=issued,
                reason_code=(
                    "dispatch_disabled" if not credential_configured else "invalid_credential"
                ),
                reason_message=detail,
                checks=checks,
                status_code=503 if not credential_configured else 401,
                result_sha256=run.result_sha256,
            ),
        )
        self._require(
            RunStatus(run.status) == RunStatus.SUCCEEDED,
            code="successful_candidate",
            label="Successful candidate",
            passed_detail="The selected optimization run completed successfully.",
            failed_detail="Only a successful optimization candidate can be dispatched.",
            checks=checks,
            rejection=lambda code, detail: self._reject_common(
                run_id, interval_index, command, correlation, requested_by, issued,
                code, detail, checks, run.result_sha256
            ),
        )
        approval = self.session.scalar(
            select(ApprovalRow).where(ApprovalRow.run_id == str(run_id))
        )
        self._require(
            approval is not None and approval.decision == ApprovalDecision.APPROVED.value,
            code="immutable_operator_approval",
            label="Immutable operator approval",
            passed_detail=(
                f"Approval by {approval.decided_by} is bound to the selected run."
                if approval else "Approval exists."
            ),
            failed_detail="The candidate does not have an immutable operator approval.",
            checks=checks,
            rejection=lambda code, detail: self._reject_common(
                run_id, interval_index, command, correlation, requested_by, issued,
                code, detail, checks, run.result_sha256
            ),
        )
        self._require(
            bool(run.result_sha256 and approval and approval.result_sha256 == run.result_sha256),
            code="approval_result_hash",
            label="Approval-result hash binding",
            passed_detail=(
                f"Approval matches result {run.result_sha256[:12]}…"
                if run.result_sha256
                else "Approval is bound to a result hash."
            ),
            failed_detail="The approval hash does not match the current result.",
            checks=checks,
            rejection=lambda code, detail: self._reject_common(
                run_id, interval_index, command, correlation, requested_by, issued,
                code, detail, checks, run.result_sha256
            ),
        )
        result = run.result_payload or {}
        self._require(
            (result.get("validation") or {}).get("passed") is True,
            code="deterministic_validation",
            label="Deterministic validation",
            passed_detail="The optimizer result passed deterministic validation.",
            failed_detail="The candidate lacks passing deterministic validation.",
            checks=checks,
            rejection=lambda code, detail: self._reject_common(
                run_id, interval_index, command, correlation, requested_by, issued,
                code, detail, checks, run.result_sha256
            ),
        )
        buy, sell = result.get("w_buy"), result.get("w_sell")
        series_valid = (
            isinstance(buy, list) and isinstance(sell, list) and len(buy) == len(sell)
        )
        self._require(
            series_valid and interval_index <= len(buy),
            code="interval_in_horizon",
            label="Interval in approved horizon",
            passed_detail=f"Interval {interval_index} is inside the immutable result horizon.",
            failed_detail="The requested interval is outside the optimized horizon.",
            checks=checks,
            rejection=lambda code, detail: self._reject_common(
                run_id, interval_index, command, correlation, requested_by, issued,
                code, detail, checks, run.result_sha256
            ),
        )
        input_data = self.input_registry.load(run.input_reference, run.input_sha256)
        interval_minutes = int(input_data.get("timestep_minutes") or 0)
        capacity_kw = sum(
            float(charger.get("charger_kw", charger.get("max_power_kw", 0.0)))
            for charger in input_data.get("chargers", [])
        )
        index = interval_index - 1
        setpoint_kw = (float(buy[index]) - float(sell[index])) * 60.0 / interval_minutes
        self._require(
            math.isfinite(setpoint_kw) and abs(setpoint_kw) <= capacity_kw + 1e-7,
            code="site_capacity_envelope",
            label="Site capacity envelope",
            passed_detail=f"{setpoint_kw:.1f} kW is inside the ±{capacity_kw:.1f} kW envelope.",
            failed_detail="The derived setpoint is non-finite or exceeds site capacity.",
            checks=checks,
            rejection=lambda code, detail: self._reject_common(
                run_id, interval_index, command, correlation, requested_by, issued,
                code, detail, checks, run.result_sha256, setpoint_kw
            ),
        )
        if self.gateway is None:
            return self._reject(
                run_id=run_id,
                interval_index=interval_index,
                command_id=command,
                correlation_id=correlation,
                requested_by=requested_by,
                issued_at=issued,
                reason_code="ot_gateway_disabled",
                reason_message="The synthetic OT gateway is not configured.",
                checks=checks,
                status_code=503,
                result_sha256=run.result_sha256,
                setpoint_kw=setpoint_kw,
                decision="failed",
            )
        try:
            controller = self.gateway.dispatch(
                GatewayDispatchRequest(
                    command_id=command,
                    correlation_id=correlation,
                    issued_at=issued,
                    expires_at=expires,
                    setpoint_kw=setpoint_kw,
                    site_capacity_kw=capacity_kw,
                    result_sha256=run.result_sha256,
                )
            )
        except GatewayPolicyError as exc:
            return self._reject(
                run_id=run_id,
                interval_index=interval_index,
                command_id=command,
                correlation_id=correlation,
                requested_by=requested_by,
                issued_at=issued,
                reason_code=exc.code,
                reason_message=str(exc),
                checks=checks,
                status_code=409,
                result_sha256=run.result_sha256,
                setpoint_kw=setpoint_kw,
            )
        except GatewayUnavailableError as exc:
            return self._reject(
                run_id=run_id,
                interval_index=interval_index,
                command_id=command,
                correlation_id=correlation,
                requested_by=requested_by,
                issued_at=issued,
                reason_code=exc.code,
                reason_message=str(exc),
                checks=checks,
                status_code=503,
                result_sha256=run.result_sha256,
                setpoint_kw=setpoint_kw,
                decision="failed",
            )
        payload = controller.model_dump(mode="json")
        return self._persist(
            run_id=run_id,
            interval_index=interval_index,
            command_id=command,
            correlation_id=correlation,
            action="dispatch",
            decision="accepted",
            reason_code="dispatch_applied",
            reason_message="Approved schedule interval was applied to the synthetic controller.",
            setpoint_kw=setpoint_kw,
            result_sha256=run.result_sha256,
            modbus_frame_hex=controller.frame_hex,
            response_frame_hex=controller.response_frame_hex,
            checks=checks,
            controller_response=payload,
            requested_by=requested_by,
            issued_at=issued,
            event_type="approved_dispatch_applied",
            severity="info",
            outcome="accepted",
        )

    def safe_state(
        self,
        *,
        reason: str,
        requested_by: str,
        credential_accepted: bool,
        credential_configured: bool,
    ) -> OTDispatchAttemptResponse:
        issued, command, correlation = utc_now(), uuid4(), uuid4()
        checks = [
            DispatchPolicyCheckResponse(
                code="separate_emergency_credential",
                label="Separate emergency credential",
                passed=credential_configured and credential_accepted,
                detail=(
                    "A separately configured emergency credential was accepted."
                    if credential_configured and credential_accepted
                    else "The separately configured emergency credential was unavailable or rejected."
                ),
            )
        ]
        if not credential_configured or not credential_accepted:
            return self._reject(
                run_id=None,
                interval_index=None,
                command_id=command,
                correlation_id=correlation,
                requested_by=requested_by,
                issued_at=issued,
                reason_code=(
                    "safe_state_disabled" if not credential_configured else "invalid_credential"
                ),
                reason_message=checks[0].detail,
                checks=checks,
                status_code=503 if not credential_configured else 401,
                result_sha256=None,
                action="safe_state",
            )
        if self.gateway is None:
            return self._reject(
                run_id=None,
                interval_index=None,
                command_id=command,
                correlation_id=correlation,
                requested_by=requested_by,
                issued_at=issued,
                reason_code="ot_gateway_disabled",
                reason_message="The synthetic OT gateway is not configured.",
                checks=checks,
                status_code=503,
                result_sha256=None,
                action="safe_state",
                decision="failed",
            )
        try:
            controller = self.gateway.safe_state(
                GatewaySafeStateRequest(
                    command_id=command,
                    correlation_id=correlation,
                    issued_at=issued,
                    expires_at=issued + timedelta(seconds=20),
                    reason=reason,
                )
            )
        except (GatewayPolicyError, GatewayUnavailableError) as exc:
            return self._reject(
                run_id=None,
                interval_index=None,
                command_id=command,
                correlation_id=correlation,
                requested_by=requested_by,
                issued_at=issued,
                reason_code=exc.code,
                reason_message=str(exc),
                checks=checks,
                status_code=503 if isinstance(exc, GatewayUnavailableError) else 409,
                result_sha256=None,
                action="safe_state",
                decision="failed" if isinstance(exc, GatewayUnavailableError) else "rejected",
            )
        payload = controller.model_dump(mode="json")
        return self._persist(
            run_id=None,
            interval_index=None,
            command_id=command,
            correlation_id=correlation,
            action="safe_state",
            decision="accepted",
            reason_code="emergency_safe_state_activated",
            reason_message=reason,
            setpoint_kw=0.0,
            result_sha256=None,
            modbus_frame_hex=controller.frame_hex,
            response_frame_hex=controller.response_frame_hex,
            checks=checks,
            controller_response=payload,
            requested_by=requested_by,
            issued_at=issued,
            event_type="emergency_safe_state_activated",
            severity="high",
            outcome="accepted",
        )

    def list_attempts(
        self, *, run_id: UUID | None, limit: int, offset: int
    ) -> list[OTDispatchAttemptResponse]:
        query = select(OTDispatchAttemptRow)
        if run_id is not None:
            query = query.where(OTDispatchAttemptRow.run_id == str(run_id))
        rows = self.session.scalars(
            query.order_by(OTDispatchAttemptRow.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return [dispatch_attempt_response(row) for row in rows]

    def list_events(self, *, limit: int, offset: int) -> list[SecurityEventResponse]:
        rows = self.session.scalars(
            select(SecurityEventRow)
            .order_by(SecurityEventRow.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [security_event_response(row) for row in rows]

    def _require(
        self,
        condition: bool,
        *,
        code: str,
        label: str,
        passed_detail: str,
        failed_detail: str,
        checks: list[DispatchPolicyCheckResponse],
        rejection,
    ) -> None:
        checks.append(
            DispatchPolicyCheckResponse(
                code=code,
                label=label,
                passed=condition,
                detail=passed_detail if condition else failed_detail,
            )
        )
        if not condition:
            rejection(code, failed_detail)

    def _reject_common(
        self, run_id, interval_index, command_id, correlation_id, requested_by,
        issued_at, code, detail, checks, result_sha256, setpoint_kw=None
    ):
        return self._reject(
            run_id=run_id,
            interval_index=interval_index,
            command_id=command_id,
            correlation_id=correlation_id,
            requested_by=requested_by,
            issued_at=issued_at,
            reason_code=code,
            reason_message=detail,
            checks=checks,
            status_code=409,
            result_sha256=result_sha256,
            setpoint_kw=setpoint_kw,
        )

    def _reject(
        self,
        *,
        run_id,
        interval_index,
        command_id,
        correlation_id,
        requested_by,
        issued_at,
        reason_code,
        reason_message,
        checks,
        status_code,
        result_sha256,
        setpoint_kw=None,
        action="dispatch",
        decision="rejected",
    ):
        attempt = self._persist(
            run_id=run_id,
            interval_index=interval_index,
            command_id=command_id,
            correlation_id=correlation_id,
            action=action,
            decision=decision,
            reason_code=reason_code,
            reason_message=reason_message,
            setpoint_kw=setpoint_kw,
            result_sha256=result_sha256,
            modbus_frame_hex=None,
            response_frame_hex=None,
            checks=checks,
            controller_response=None,
            requested_by=requested_by,
            issued_at=issued_at,
            event_type=(
                "controller_exchange_failed" if decision == "failed" else "dispatch_rejected"
            ),
            severity="high" if reason_code in {"invalid_credential", "replayed_command"} else "medium",
            outcome=decision,
        )
        raise DispatchRejectedError(attempt, status_code)

    def _persist(
        self,
        *,
        run_id,
        interval_index,
        command_id,
        correlation_id,
        action,
        decision,
        reason_code,
        reason_message,
        setpoint_kw,
        result_sha256,
        modbus_frame_hex,
        response_frame_hex,
        checks,
        controller_response,
        requested_by,
        issued_at,
        event_type,
        severity,
        outcome,
    ) -> OTDispatchAttemptResponse:
        completed = utc_now()
        row = OTDispatchAttemptRow(
            id=str(uuid4()),
            run_id=str(run_id) if run_id else None,
            interval_index=interval_index,
            command_id=str(command_id),
            correlation_id=str(correlation_id),
            action=action,
            decision=decision,
            reason_code=reason_code,
            reason_message=reason_message,
            setpoint_kw=setpoint_kw,
            result_sha256=result_sha256,
            modbus_frame_hex=modbus_frame_hex,
            response_frame_hex=response_frame_hex,
            policy_checks=[check.model_dump(mode="json") for check in checks],
            controller_response=controller_response,
            requested_by=requested_by,
            issued_at=issued_at,
            completed_at=completed,
            created_at=completed,
        )
        event = SecurityEventRow(
            id=str(uuid4()),
            event_type=event_type,
            severity=severity,
            correlation_id=str(correlation_id),
            run_id=str(run_id) if run_id else None,
            actor=requested_by,
            source_zone="enterprise-operator",
            destination="supervisory-gateway",
            outcome=outcome,
            reason_code=reason_code,
            details={
                "action": action,
                "attempt_id": row.id,
                "command_id": str(command_id),
                "interval_index": interval_index,
                "setpoint_kw": setpoint_kw,
                "policy_version": self.POLICY_VERSION,
                "simulated_only": True,
            },
            occurred_at=completed,
        )
        self.session.add_all([row, event])
        self.session.commit()
        return dispatch_attempt_response(row)
