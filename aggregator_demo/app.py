from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import __version__
from .approval_repository import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    ApprovalRepository,
)
from .contracts import (
    AgentBackend,
    ApprovalCreateRequest,
    ApprovalResponse,
    CapabilityResponse,
    DemoInputListResponse,
    ErrorResponse,
    FailureDrillCreateRequest,
    HealthResponse,
    NoticeCreateRequest,
    NoticeListResponse,
    NoticeResponse,
    RunCreateRequest,
    RunListResponse,
    RunResponse,
    RunResultResponse,
    RunStatus,
    RunTimelineResponse,
    RunType,
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
from .notice_repository import (
    NoticeConflictError,
    NoticeNotFoundError,
    NoticeRepository,
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
        title="DepotFlux Industry Demonstrator",
        description=(
            "Human-approved decision support for electric-fleet charging and "
            "real-time replanning. This API does not control physical assets."
        ),
        version=__version__,
    )
    application.state.database_engine = engine
    application.state.session_factory = create_session_factory(engine)
    application.state.input_registry = DemoInputRegistry(input_root)
    allowed_origins = [
        origin.strip()
        for origin in os.environ.get(
            "DEMO_ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,"
            "https://agentic-aggregator-ops.soft-ape-5410.chatgpt.site,"
            "https://depotflux-ops.soft-ape-5410.chatgpt.site",
        ).split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-Operator-ID"],
    )

    @application.get(
        "/health/live",
        response_model=HealthResponse,
        response_model_exclude_none=True,
        tags=["health"],
        summary="Process liveness",
    )
    def liveness() -> HealthResponse:
        return HealthResponse(
            service="depotflux-api",
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
                service="depotflux-api",
                status="ok",
                version=__version__,
            )
        except SQLAlchemyError:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(
                service="depotflux-api",
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
        "/api/v1/failure-drills",
        response_model=RunResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["runs"],
        summary="Queue a controlled solver failure for an operator drill",
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def create_failure_drill(
        request: FailureDrillCreateRequest,
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
                RunCreateRequest(
                    run_type=RunType.DAY_AHEAD,
                    input_reference=request.input_reference,
                    input_sha256=request.input_sha256,
                    v2g_enabled=True,
                    agent_backend=AgentBackend.RULE,
                    scenario_ids=[f"failure_drill:{request.drill_type.value}"],
                ),
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
        "/api/v1/runs/{run_id}/approval",
        response_model=ApprovalResponse,
        tags=["approvals"],
        summary="Get the immutable operator decision for a candidate",
        responses={404: {"model": ErrorResponse}},
    )
    def get_approval(run_id: UUID, session: SessionDependency):
        try:
            return ApprovalRepository(session).get(run_id)
        except ApprovalNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="approval_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.post(
        "/api/v1/runs/{run_id}/approval",
        response_model=ApprovalResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["approvals"],
        summary="Record an immutable human approval or rejection",
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    def create_approval(
        run_id: UUID,
        request: ApprovalCreateRequest,
        session: SessionDependency,
        operator_id: Annotated[
            str,
            Header(alias="X-Operator-ID", min_length=1, max_length=128),
        ] = "demo-operator",
    ):
        try:
            return ApprovalRepository(session).create(
                run_id,
                request,
                decided_by=operator_id,
            )
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="run_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except ApprovalConflictError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ErrorResponse(
                    code="approval_conflict",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/runs/{run_id}/timeline",
        response_model=RunTimelineResponse,
        tags=["audit"],
        summary="Get the persisted run and decision timeline",
        responses={404: {"model": ErrorResponse}},
    )
    def get_timeline(run_id: UUID, session: SessionDependency):
        try:
            return ApprovalRepository(session).timeline(run_id)
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="run_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.post(
        "/api/v1/notices/simulate",
        response_model=NoticeResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["notices"],
        summary="Create a frozen operational notice and queue a replanning run",
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    def simulate_notice(
        request: NoticeCreateRequest,
        session: SessionDependency,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", min_length=1, max_length=120),
        ] = None,
        operator_id: Annotated[
            str,
            Header(alias="X-Operator-ID", min_length=1, max_length=128),
        ] = "demo-operator",
    ):
        try:
            return NoticeRepository(session).create_simulated(
                request,
                created_by=operator_id,
                idempotency_key=idempotency_key,
            )
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="baseline_run_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except (NoticeConflictError, RunConflictError) as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ErrorResponse(
                    code="notice_conflict",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/notices",
        response_model=NoticeListResponse,
        tags=["notices"],
        summary="List simulated operational notices",
    )
    def list_notices(
        session: SessionDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> NoticeListResponse:
        return NoticeListResponse(
            items=NoticeRepository(session).list(limit=limit, offset=offset),
            limit=limit,
            offset=offset,
        )

    @application.get(
        "/api/v1/notices/{notice_id}",
        response_model=NoticeResponse,
        tags=["notices"],
        summary="Get a preserved operational notice and interpretation",
        responses={404: {"model": ErrorResponse}},
    )
    def get_notice(notice_id: UUID, session: SessionDependency):
        try:
            return NoticeRepository(session).get(notice_id)
        except NoticeNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="notice_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/runs/{run_id}/notice",
        response_model=NoticeResponse,
        tags=["notices"],
        summary="Get the operational notice linked to a replanning run",
        responses={404: {"model": ErrorResponse}},
    )
    def get_run_notice(run_id: UUID, session: SessionDependency):
        try:
            return NoticeRepository(session).get_by_candidate(run_id)
        except NoticeNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="notice_not_found",
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
