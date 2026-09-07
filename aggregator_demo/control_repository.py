from __future__ import annotations

import math
from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .contracts import (
    ApprovalDecision,
    ControlPolicyCheckResponse,
    ControlSimulationResponse,
    RunStatus,
)
from .database import ApprovalRow, ControlSimulationRow, RunRow, utc_now
from .input_registry import DemoInputRegistry
from .ot_security import (
    SITE_POWER_REGISTER,
    SITE_POWER_SCALE_KW,
    ControlPolicyError,
    encode_site_power_write,
    validate_site_setpoint,
)
from .run_repository import RunNotFoundError


def _as_utc(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def control_simulation_response(row: ControlSimulationRow) -> ControlSimulationResponse:
    return ControlSimulationResponse(
        id=UUID(row.id),
        run_id=UUID(row.run_id),
        interval_index=row.interval_index,
        setpoint_kw=row.setpoint_kw,
        unit_id=row.unit_id,
        register_address=row.register_address,
        register_scale_kw=row.register_scale_kw,
        modbus_frame_hex=row.modbus_frame_hex,
        result_sha256=row.result_sha256,
        policy_version=row.policy_version,
        policy_checks=row.policy_checks,
        simulated_only=True,
        requested_by=row.requested_by,
        created_at=_as_utc(row.created_at),
    )


class ControlSimulationRepository:
    def __init__(self, session: Session, input_registry: DemoInputRegistry):
        self.session = session
        self.input_registry = input_registry

    def create(
        self,
        run_id: UUID,
        *,
        interval_index: int,
        requested_by: str,
    ) -> ControlSimulationResponse:
        run = self.session.get(RunRow, str(run_id))
        if run is None:
            raise RunNotFoundError(f"run {run_id} was not found")
        existing = self._find(run_id, interval_index)
        if existing is not None:
            return control_simulation_response(existing)

        approval = self.session.scalar(
            select(ApprovalRow).where(ApprovalRow.run_id == str(run_id))
        )
        if approval is None or approval.decision != ApprovalDecision.APPROVED.value:
            raise ControlPolicyError(
                "candidate requires an immutable operator approval",
                failed_check="immutable_operator_approval",
            )
        if RunStatus(run.status) != RunStatus.SUCCEEDED:
            raise ControlPolicyError(
                "only a successful candidate can be simulated",
                failed_check="successful_candidate",
            )
        if not run.result_sha256 or approval.result_sha256 != run.result_sha256:
            raise ControlPolicyError(
                "approved result hash does not match the candidate",
                failed_check="approval_result_hash",
            )
        result = run.result_payload or {}
        if (result.get("validation") or {}).get("passed") is not True:
            raise ControlPolicyError(
                "candidate lacks passing deterministic validation",
                failed_check="deterministic_validation",
            )

        buy = result.get("w_buy")
        sell = result.get("w_sell")
        if not isinstance(buy, list) or not isinstance(sell, list) or len(buy) != len(sell):
            raise ControlPolicyError(
                "candidate site-power series is unavailable",
                failed_check="site_power_series",
            )
        if interval_index > len(buy):
            raise ControlPolicyError(
                "requested interval is outside the optimized horizon",
                failed_check="interval_in_horizon",
            )

        input_data = self.input_registry.load(run.input_reference, run.input_sha256)
        interval_minutes = int(input_data.get("timestep_minutes") or 0)
        if interval_minutes <= 0:
            raise ControlPolicyError(
                "input interval duration is invalid",
                failed_check="input_interval_duration",
            )
        capacity_kw = sum(
            float(charger.get("charger_kw", charger.get("max_power_kw", 0.0)))
            for charger in input_data.get("chargers", [])
        )
        interval = interval_index - 1
        net_energy_kwh = float(buy[interval]) - float(sell[interval])
        if not math.isfinite(net_energy_kwh):
            raise ControlPolicyError(
                "candidate site-power value is not finite",
                failed_check="finite_site_setpoint",
            )
        setpoint_kw = validate_site_setpoint(
            net_energy_kwh * 60.0 / interval_minutes,
            site_capacity_kw=capacity_kw,
        )

        dispatch_id = uuid4()
        frame = encode_site_power_write(
            setpoint_kw,
            transaction_id=interval_index & 0xFFFF,
        )
        policy_checks = [
            ControlPolicyCheckResponse(
                code="immutable_operator_approval",
                label="Immutable approval",
                detail=f"Approved by {approval.decided_by} and bound to the selected run.",
            ),
            ControlPolicyCheckResponse(
                code="approval_result_hash",
                label="Result hash binding",
                detail=f"Approval matches result {run.result_sha256[:12]}…",
            ),
            ControlPolicyCheckResponse(
                code="deterministic_validation",
                label="Deterministic validation",
                detail="The optimizer result passed all deterministic validation checks.",
            ),
            ControlPolicyCheckResponse(
                code="interval_in_horizon",
                label="Interval in horizon",
                detail=f"Interval {interval_index} is within the {len(buy)}-interval result.",
            ),
            ControlPolicyCheckResponse(
                code="site_capacity_envelope",
                label="Site capacity envelope",
                detail=f"{setpoint_kw:.1f} kW is within the ±{capacity_kw:.1f} kW envelope.",
            ),
            ControlPolicyCheckResponse(
                code="signed_register_range",
                label="Register representation",
                detail="The setpoint is representable as a signed 16-bit value at 0.1 kW scale.",
            ),
        ]
        row = ControlSimulationRow(
            id=str(dispatch_id),
            run_id=str(run_id),
            interval_index=interval_index,
            setpoint_kw=setpoint_kw,
            unit_id=1,
            register_address=SITE_POWER_REGISTER,
            register_scale_kw=SITE_POWER_SCALE_KW,
            modbus_frame_hex=frame.hex(),
            result_sha256=run.result_sha256,
            policy_version="ot-policy-v1",
            policy_checks=[check.model_dump(mode="json") for check in policy_checks],
            requested_by=requested_by,
            created_at=utc_now(),
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self._find(run_id, interval_index)
            if existing is None:
                raise
            return control_simulation_response(existing)
        return control_simulation_response(row)

    def list(self, run_id: UUID) -> list[ControlSimulationResponse]:
        if self.session.get(RunRow, str(run_id)) is None:
            raise RunNotFoundError(f"run {run_id} was not found")
        rows = self.session.scalars(
            select(ControlSimulationRow)
            .where(ControlSimulationRow.run_id == str(run_id))
            .order_by(ControlSimulationRow.interval_index)
        ).all()
        return [control_simulation_response(row) for row in rows]

    def _find(self, run_id: UUID, interval_index: int) -> ControlSimulationRow | None:
        return self.session.scalar(
            select(ControlSimulationRow).where(
                ControlSimulationRow.run_id == str(run_id),
                ControlSimulationRow.interval_index == interval_index,
            )
        )
