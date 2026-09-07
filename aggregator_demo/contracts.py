from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class HealthResponse(StrictContract):
    service: str
    status: Literal["ok"]
    version: str


class CapabilityResponse(StrictContract):
    api_version: Literal["v1"]
    product_level: Literal["industry_demonstrator"]
    operating_boundary: Literal["human_approved_decision_support"]
    direct_asset_control: Literal[False] = False
    run_statuses: list[RunStatus]
