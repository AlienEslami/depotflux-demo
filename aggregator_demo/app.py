from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .contracts import CapabilityResponse, HealthResponse, RunStatus


def create_app() -> FastAPI:
    application = FastAPI(
        title="Agentic Aggregator Industry Demonstrator",
        description=(
            "Human-approved decision support for electric-fleet charging and "
            "real-time replanning. This API does not control physical assets."
        ),
        version=__version__,
    )

    @application.get(
        "/health/live",
        response_model=HealthResponse,
        tags=["health"],
        summary="Process liveness",
    )
    def liveness() -> HealthResponse:
        return HealthResponse(
            service="agentic-aggregator-api",
            status="ok",
            version=__version__,
        )

    @application.get(
        "/health/ready",
        response_model=HealthResponse,
        tags=["health"],
        summary="Application readiness",
    )
    def readiness() -> HealthResponse:
        # Database, queue, and solver probes are added with the durable backend.
        return HealthResponse(
            service="agentic-aggregator-api",
            status="ok",
            version=__version__,
        )

    @application.get(
        "/api/v1/meta",
        response_model=CapabilityResponse,
        tags=["system"],
        summary="Versioned demonstrator capabilities and operating boundary",
    )
    def capabilities() -> CapabilityResponse:
        return CapabilityResponse(
            api_version="v1",
            product_level="industry_demonstrator",
            operating_boundary="human_approved_decision_support",
            direct_asset_control=False,
            run_statuses=list(RunStatus),
        )

    return application


app = create_app()
