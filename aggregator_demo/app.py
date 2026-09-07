from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import __version__
from .contracts import (
    CapabilityResponse,
    DemoInputListResponse,
    ErrorResponse,
    HealthResponse,
    RunCreateRequest,
    RunListResponse,
    RunResponse,
    RunResultResponse,
    RunStatus,
)
from .database import (
    create_database_engine,
    create_schema,
    create_session_factory,
    ping_database,
)
from .input_registry import (
    DemoInputIntegrityError,
    DemoInputNotFoundError,
    DemoInputRegistry,
)
from .run_repository import RunConflictError, RunNotFoundError, RunRepository


def database_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


SessionDependency = Annotated[Session, Depends(database_session)]


def _environment_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(
    *,
    database_url: str | None = None,
    initialize_schema: bool | None = None,
    input_root: Path | None = None,
) -> FastAPI:
    engine = create_database_engine(database_url)
    if initialize_schema is None:
        initialize_schema = _environment_flag("DEMO_AUTO_CREATE_SCHEMA", True)
    if initialize_schema:
        create_schema(engine)

    application = FastAPI(
        title="Agentic Aggregator Industry Demonstrator",
        description=(
            "Human-approved decision support for electric-fleet charging and "
            "real-time replanning. This API does not control physical assets."
        ),
        version=__version__,
    )
    application.state.database_engine = engine
    application.state.session_factory = create_session_factory(engine)
    application.state.input_registry = DemoInputRegistry(input_root)

    @application.get(
        "/health/live",
        response_model=HealthResponse,
        response_model_exclude_none=True,
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
        response_model_exclude_none=True,
        tags=["health"],
        summary="Application readiness",
    )
    def readiness(response: Response) -> HealthResponse:
        try:
            ping_database(application.state.database_engine)
            return HealthResponse(
                service="agentic-aggregator-api",
                status="ok",
                version=__version__,
            )
        except SQLAlchemyError:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(
                service="agentic-aggregator-api",
                status="unavailable",
                version=__version__,
                detail="database unavailable",
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

    @application.get(
        "/api/v1/inputs",
        response_model=DemoInputListResponse,
        tags=["inputs"],
        summary="List immutable inputs bundled with the demonstrator",
    )
    def list_demo_inputs() -> DemoInputListResponse:
        return DemoInputListResponse(items=application.state.input_registry.list())

    @application.post(
        "/api/v1/runs",
        response_model=RunResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["runs"],
        summary="Submit an idempotent optimization run",
        responses={409: {"model": ErrorResponse}},
    )
    def create_run(
        request: RunCreateRequest,
        session: SessionDependency,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", min_length=1, max_length=128),
        ] = None,
        operator_id: Annotated[
            str,
            Header(alias="X-Operator-ID", min_length=1, max_length=128),
        ] = "demo-operator",
    ):
        try:
            application.state.input_registry.verify(
                request.input_reference,
                request.input_sha256,
            )
            created_run, _ = RunRepository(session).create(
                request,
                requested_by=operator_id,
                idempotency_key=idempotency_key,
            )
            return created_run
        except DemoInputNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content=ErrorResponse(
                    code=exc.code,
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except DemoInputIntegrityError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ErrorResponse(
                    code=exc.code,
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except RunConflictError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ErrorResponse(
                    code="idempotency_conflict",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/runs/{run_id}",
        response_model=RunResponse,
        tags=["runs"],
        summary="Get a persisted optimization run",
        responses={404: {"model": ErrorResponse}},
    )
    def get_run(run_id: UUID, session: SessionDependency):
        try:
            return RunRepository(session).get(run_id)
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="run_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/runs/{run_id}/result",
        response_model=RunResultResponse,
        tags=["runs"],
        summary="Get a terminal run result or explicit failure",
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    def get_run_result(run_id: UUID, session: SessionDependency):
        try:
            return RunRepository(session).result(run_id)
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="run_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except RunConflictError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ErrorResponse(
                    code="run_not_complete",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/runs",
        response_model=RunListResponse,
        tags=["runs"],
        summary="List persisted optimization runs",
    )
    def list_runs(
        session: SessionDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> RunListResponse:
        return RunListResponse(
            items=RunRepository(session).list(limit=limit, offset=offset),
            limit=limit,
            offset=offset,
        )

    @application.post(
        "/api/v1/runs/{run_id}/cancel",
        response_model=RunResponse,
        tags=["runs"],
        summary="Request cancellation of a non-terminal run",
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    def cancel_run(run_id: UUID, session: SessionDependency):
        try:
            return RunRepository(session).request_cancellation(run_id)
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="run_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except RunConflictError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ErrorResponse(
                    code="run_state_conflict",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    return application


app = create_app()
