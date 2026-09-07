from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictContract(BaseModel):
    """Base for public API contracts; unexpected fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class RunStatus(StrEnum):
    """Durable lifecycle states exposed by the demonstrator API."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INFEASIBLE = "infeasible"
    TIMED_OUT = "timed_out"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    DEGRADED = "degraded"

    @property
    def is_terminal(self) -> bool:
        return self in {
            self.SUCCEEDED,
            self.FAILED,
            self.INFEASIBLE,
            self.TIMED_OUT,
            self.CANCELLED,
            self.DEGRADED,
        }


class RunType(StrEnum):
    DAY_AHEAD = "day_ahead"
    REAL_TIME = "real_time"


class OptimizationMode(StrEnum):
    SELFISH = "selfish"
    ALTRUISTIC = "altruistic"


class AgentBackend(StrEnum):
    RULE = "rule"
    OPENAI = "openai"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class NoticeScenario(StrEnum):
    """Frozen simulator events available in the industry demonstrator."""

    LATE_RETURN = "late_return"
    CHARGER_DERATING = "charger_derating"
    COMBINED_DISRUPTION = "combined_disruption"
    SITE_POWER_ISOLATION = "site_power_isolation"


class FailureDrillType(StrEnum):
    """Controlled, operator-visible failure cases for the demonstrator."""

    INFEASIBLE = "infeasible"
    SOLVER_TIMEOUT = "solver_timeout"


class RunCreateRequest(StrictContract):
    run_type: RunType
    optimization_mode: OptimizationMode = OptimizationMode.SELFISH
    input_reference: str = Field(min_length=1, max_length=255)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    v2g_enabled: bool = True
    agent_backend: AgentBackend = AgentBackend.RULE
    scenario_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("scenario_ids")
    @classmethod
    def unique_nonempty_scenarios(cls, value: list[str]) -> list[str]:
        normalized = [scenario.strip() for scenario in value]
        if any(not scenario for scenario in normalized):
            raise ValueError("scenario_ids may not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("scenario_ids must be unique")
        return normalized


class RunResponse(StrictContract):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    status: RunStatus
    run_type: RunType
    optimization_mode: OptimizationMode
    input_reference: str
    input_sha256: str
    v2g_enabled: bool
    agent_backend: AgentBackend
    scenario_ids: list[str]
    requested_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    recovery_count: int = Field(ge=0)
    last_recovered_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class RunListResponse(StrictContract):
    items: list[RunResponse]
    limit: int
    offset: int


class RunResultResponse(StrictContract):
    run_id: UUID
    status: RunStatus
    solver_name: str | None = None
    result_sha256: str | None = None
    result: dict | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class ApprovalCreateRequest(StrictContract):
    decision: ApprovalDecision
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ApprovalResponse(StrictContract):
    id: UUID
    run_id: UUID
    decision: ApprovalDecision
    decided_by: str
    result_sha256: str
    note: str | None = None
    created_at: datetime


class AuditEventResponse(StrictContract):
    event_type: Literal[
        "notice_received",
        "run_submitted",
        "run_started",
        "run_recovered",
        "run_completed",
        "decision_recorded",
    ]
    occurred_at: datetime
    actor: str
    detail: str


class RunTimelineResponse(StrictContract):
    run_id: UUID
    events: list[AuditEventResponse]


class NoticeCreateRequest(StrictContract):
    baseline_run_id: UUID
    scenario: NoticeScenario


class FailureDrillCreateRequest(StrictContract):
    input_reference: str = Field(min_length=1, max_length=255)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    drill_type: FailureDrillType


class NoticeResponse(StrictContract):
    id: UUID
    baseline_run_id: UUID
    candidate_run_id: UUID
    scenario: NoticeScenario
    source: Literal["simulator"]
    raw_notice: str
    structured_facts: dict
    interpretation_backend: Literal["rule"]
    confidence: float = Field(ge=0, le=1)
    replan_recommended: bool
    rationale: str
    created_by: str
    created_at: datetime


class NoticeListResponse(StrictContract):
    items: list[NoticeResponse]
    limit: int
    offset: int


class DemoInputResponse(StrictContract):
    reference: str
    sha256: str
    filename: str
    depot: str
    fleet_size: int = Field(ge=1)
    charger_count: int = Field(ge=1)
    trip_count: int = Field(ge=1)
    horizon_intervals: int = Field(ge=1)
    interval_minutes: int = Field(ge=1)
    provenance: str


class DemoInputListResponse(StrictContract):
    items: list[DemoInputResponse]


class ErrorResponse(StrictContract):
    code: str
    message: str


class HealthResponse(StrictContract):
    service: str
    status: Literal["ok", "unavailable"]
    version: str
    detail: str | None = None


class CapabilityResponse(StrictContract):
    api_version: Literal["v1"]
    product_level: Literal["industry_demonstrator"]
    operating_boundary: Literal["human_approved_decision_support"]
    direct_asset_control: Literal[False] = False
    run_statuses: list[RunStatus]
