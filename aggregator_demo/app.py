from __future__ import annotations

import os
import logging
import time
from hmac import compare_digest
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import __version__
from .auth import (
    AuthenticationError,
    AuthMode,
    Principal,
    Role,
    require_role,
)
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
    ControlSimulationCreateRequest,
    ControlSimulationListResponse,
    ControlPolicyRejectionResponse,
    ControlSimulationResponse,
    DispatchCreateRequest,
    EmergencySafeStateRequest,
    DemoInputListResponse,
    ErrorResponse,
    FailureDrillCreateRequest,
    HealthResponse,
    NoticeCreateRequest,
    NoticeListResponse,
    NoticeResponse,
    OTDispatchAttemptListResponse,
    OTDispatchAttemptResponse,
    RunCreateRequest,
    RunListResponse,
    RunResponse,
    RunResultResponse,
    RunStatus,
    RunTimelineResponse,
    RunType,
    SecurityEventListResponse,
    SessionResponse,
)
from .control_repository import ControlSimulationRepository
from .dispatch_repository import DispatchEvidenceRepository, DispatchRejectedError
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
from .ot_security import (
    ControlAuthenticationError,
    ControlPolicyError,
    authenticate_control_key,
)
from .ot_gateway import OTGatewayClient
from .run_repository import RunConflictError, RunNotFoundError, RunRepository
from .observability import RequestMetrics, configure_logging, correlation_id
from .settings import RuntimeSettings


def database_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


SessionDependency = Annotated[Session, Depends(database_session)]
bearer_scheme = HTTPBearer(auto_error=False)


def authenticated_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    development_subject: Annotated[
        str, Header(alias="X-Operator-ID", min_length=1, max_length=128)
    ] = "demo-operator",
) -> Principal:
    authorization = (
        f"{credentials.scheme} {credentials.credentials}" if credentials else None
    )
    principal = request.app.state.auth_config.authenticate(
        authorization, development_subject=development_subject
    )
    request.state.principal = principal
    return principal


def require_roles(*roles: Role):
    allowed_roles = set(roles)

    def dependency(
        principal: Annotated[Principal, Depends(authenticated_principal)],
    ) -> Principal:
        require_role(principal, allowed_roles)
        return principal

    return dependency


AnyPrincipal = Annotated[Principal, Depends(authenticated_principal)]
OperatorPrincipal = Annotated[
    Principal, Depends(require_roles(Role.OPERATOR, Role.ADMIN))
]
ApproverPrincipal = Annotated[
    Principal, Depends(require_roles(Role.APPROVER, Role.ADMIN))
]
AdminPrincipal = Annotated[Principal, Depends(require_roles(Role.ADMIN))]


def create_app(
    *,
    database_url: str | None = None,
    initialize_schema: bool | None = None,
    input_root: Path | None = None,
    control_api_key: str | None = None,
    control_gateway=None,
    emergency_api_key: str | None = None,
    runtime_settings: RuntimeSettings | None = None,
) -> FastAPI:
    settings = runtime_settings or RuntimeSettings.from_environment()
    engine = create_database_engine(database_url or settings.database_url)
    if initialize_schema is None:
        initialize_schema = settings.auto_create_schema
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
    application.state.runtime_settings = settings
    application.state.auth_config = settings.auth
    application.state.request_metrics = RequestMetrics()
    application.state.input_registry = DemoInputRegistry(input_root)
    application.state.control_api_key = control_api_key or os.environ.get(
        "DEMO_CONTROL_API_KEY"
    )
    gateway_url = os.environ.get("DEMO_OT_GATEWAY_URL")
    gateway_key = os.environ.get("DEMO_GATEWAY_API_KEY")
    application.state.control_gateway = control_gateway or (
        OTGatewayClient(gateway_url, gateway_key)
        if gateway_url and gateway_key
        else None
    )
    application.state.emergency_api_key = emergency_api_key or os.environ.get(
        "DEMO_EMERGENCY_API_KEY"
    )
    configure_logging(settings.log_level)
    request_logger = logging.getLogger("depotflux.http")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "X-Control-Key",
            "X-Emergency-Key",
            "X-Operator-ID",
            "Authorization",
            "X-Correlation-ID",
        ],
    )

    @application.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        _request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(code=exc.code, message=str(exc)).model_dump(mode="json"),
            headers=headers,
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
        message = str(first.get("msg", "request validation failed"))
        if location:
            message = f"{location}: {message}"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                code="request_validation_failed", message=message
            ).model_dump(mode="json"),
        )

    @application.middleware("http")
    async def request_observability(request: Request, call_next):
        request_correlation_id = correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = request_correlation_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - started
            application.state.request_metrics.record(
                method=request.method,
                route="<unhandled>",
                status_code=500,
                duration_seconds=duration,
            )
            request_logger.exception(
                "request failed",
                extra={
                    "correlation_id": request_correlation_id,
                    "method": request.method,
                    "route": "<unhandled>",
                    "status_code": 500,
                    "duration_ms": round(duration * 1000, 3),
                },
            )
            raise
        duration = time.perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "<unmatched>")
        application.state.request_metrics.record(
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration_seconds=duration,
        )
        response.headers["X-Correlation-ID"] = request_correlation_id
        principal = getattr(request.state, "principal", None)
        request_logger.info(
            "request completed",
            extra={
                "correlation_id": request_correlation_id,
                "method": request.method,
                "route": route,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 3),
                "actor": getattr(principal, "subject", None),
                "role": getattr(principal, "role", None),
            },
        )
        return response

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
            authentication_mode=settings.auth.mode,
            available_roles=list(Role),
        )

    @application.get(
        "/api/v1/session",
        response_model=SessionResponse,
        tags=["system"],
        summary="Resolve the current authenticated software role",
        responses={401: {"model": ErrorResponse}},
    )
    def session(principal: AnyPrincipal) -> SessionResponse:
        return SessionResponse(
            subject=principal.subject,
            role=principal.role,
            authentication_mode=settings.auth.mode,
        )

    @application.get(
        "/metrics",
        include_in_schema=False,
        response_class=PlainTextResponse,
    )
    def metrics() -> PlainTextResponse:
        if not settings.metrics_enabled:
            return PlainTextResponse("metrics disabled\n", status_code=404)
        return PlainTextResponse(
            application.state.request_metrics.render_prometheus(),
            media_type="text/plain; version=0.0.4",
        )

    @application.get(
        "/api/v1/inputs",
        response_model=DemoInputListResponse,
        tags=["inputs"],
        summary="List immutable inputs bundled with the demonstrator",
    )
    def list_demo_inputs(_principal: AnyPrincipal) -> DemoInputListResponse:
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
        principal: OperatorPrincipal,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", min_length=1, max_length=128),
        ] = None,
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
                requested_by=principal.subject,
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
        principal: OperatorPrincipal,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", min_length=1, max_length=128),
        ] = None,
    ):
        try:
            application.state.input_registry.verify(
                request.input_reference,
                request.input_sha256,
            )
            created_run, _ = RunRepository(session).create(
                request,
                requested_by=principal.subject,
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
    def get_run(run_id: UUID, session: SessionDependency, _principal: AnyPrincipal):
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
    def get_run_result(
        run_id: UUID, session: SessionDependency, _principal: AnyPrincipal
    ):
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
    def get_approval(
        run_id: UUID, session: SessionDependency, _principal: AnyPrincipal
    ):
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
        principal: ApproverPrincipal,
    ):
        try:
            return ApprovalRepository(session).create(
                run_id,
                request,
                decided_by=principal.subject,
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
    def get_timeline(
        run_id: UUID, session: SessionDependency, _principal: AnyPrincipal
    ):
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
        principal: OperatorPrincipal,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", min_length=1, max_length=120),
        ] = None,
    ):
        try:
            return NoticeRepository(session).create_simulated(
                request,
                created_by=principal.subject,
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
        _principal: AnyPrincipal,
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
    def get_notice(
        notice_id: UUID, session: SessionDependency, _principal: AnyPrincipal
    ):
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
    def get_run_notice(
        run_id: UUID, session: SessionDependency, _principal: AnyPrincipal
    ):
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
        _principal: AnyPrincipal,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> RunListResponse:
        return RunListResponse(
            items=RunRepository(session).list(limit=limit, offset=offset),
            limit=limit,
            offset=offset,
        )

    @application.post(
        "/api/v1/runs/{run_id}/dispatch-simulations",
        response_model=OTDispatchAttemptResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["ot-security"],
        summary="Dispatch one approved schedule interval through the synthetic OT path",
        responses={
            401: {"model": OTDispatchAttemptResponse},
            404: {"model": ErrorResponse},
            409: {"model": OTDispatchAttemptResponse},
            503: {"model": OTDispatchAttemptResponse},
        },
    )
    def create_dispatch_simulation(
        run_id: UUID,
        request: DispatchCreateRequest,
        session: SessionDependency,
        principal: OperatorPrincipal,
        control_key: Annotated[
            str | None,
            Header(alias="X-Control-Key", max_length=256),
        ] = None,
    ):
        configured = application.state.control_api_key
        accepted = bool(
            configured and control_key and compare_digest(control_key, configured)
        )
        try:
            return DispatchEvidenceRepository(
                session,
                application.state.input_registry,
                application.state.control_gateway,
            ).dispatch(
                run_id,
                interval_index=request.interval_index,
                requested_by=principal.subject,
                credential_accepted=accepted,
                credential_configured=bool(configured),
                command_id=request.command_id,
                issued_at=request.issued_at,
                expires_at=request.expires_at,
            )
        except DispatchRejectedError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.attempt.model_dump(mode="json"),
            )
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="run_not_found", message=str(exc)
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/runs/{run_id}/dispatch-simulations",
        response_model=OTDispatchAttemptListResponse,
        tags=["ot-security"],
        summary="List accepted, rejected, and failed synthetic dispatch attempts",
        responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def list_dispatch_simulations(
        run_id: UUID,
        session: SessionDependency,
        _principal: AnyPrincipal,
        control_key: Annotated[
            str | None,
            Header(alias="X-Control-Key", max_length=256),
        ] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        try:
            authenticate_control_key(control_key, application.state.control_api_key)
            return OTDispatchAttemptListResponse(
                items=DispatchEvidenceRepository(
                    session,
                    application.state.input_registry,
                    application.state.control_gateway,
                ).list_attempts(run_id=run_id, limit=limit, offset=offset),
                limit=limit,
                offset=offset,
            )
        except ControlAuthenticationError as exc:
            disabled = not application.state.control_api_key
            return JSONResponse(
                status_code=(503 if disabled else 401),
                content=ErrorResponse(
                    code="dispatch_disabled" if disabled else "control_authentication_failed",
                    message=str(exc),
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/security/events",
        response_model=SecurityEventListResponse,
        tags=["ot-security"],
        summary="List structured synthetic OT security events",
    )
    def list_security_events(
        session: SessionDependency,
        _principal: AnyPrincipal,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> SecurityEventListResponse:
        return SecurityEventListResponse(
            items=DispatchEvidenceRepository(
                session,
                application.state.input_registry,
                application.state.control_gateway,
            ).list_events(limit=limit, offset=offset),
            limit=limit,
            offset=offset,
        )

    @application.post(
        "/api/v1/emergency-safe-state",
        response_model=OTDispatchAttemptResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["ot-security"],
        summary="Activate zero-power safe state on the synthetic controller",
        responses={
            401: {"model": OTDispatchAttemptResponse},
            409: {"model": OTDispatchAttemptResponse},
            503: {"model": OTDispatchAttemptResponse},
        },
    )
    def activate_emergency_safe_state(
        request: EmergencySafeStateRequest,
        session: SessionDependency,
        principal: AdminPrincipal,
        emergency_key: Annotated[
            str | None,
            Header(alias="X-Emergency-Key", max_length=256),
        ] = None,
    ):
        configured = application.state.emergency_api_key
        accepted = bool(
            configured and emergency_key and compare_digest(emergency_key, configured)
        )
        try:
            return DispatchEvidenceRepository(
                session,
                application.state.input_registry,
                application.state.control_gateway,
            ).safe_state(
                reason=request.reason,
                requested_by=principal.subject,
                credential_accepted=accepted,
                credential_configured=bool(configured),
            )
        except DispatchRejectedError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.attempt.model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/controller-status",
        tags=["ot-security"],
        summary="Read the synthetic controller heartbeat through the gateway",
        responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def controller_status(
        _principal: AnyPrincipal,
        control_key: Annotated[
            str | None,
            Header(alias="X-Control-Key", max_length=256),
        ] = None,
    ):
        try:
            authenticate_control_key(control_key, application.state.control_api_key)
            if application.state.control_gateway is None:
                raise RuntimeError("synthetic OT gateway is not configured")
            return application.state.control_gateway.controller_status()
        except ControlAuthenticationError as exc:
            disabled = not application.state.control_api_key
            return JSONResponse(
                status_code=503 if disabled else 401,
                content=ErrorResponse(
                    code="dispatch_disabled" if disabled else "control_authentication_failed",
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except Exception:
            return JSONResponse(
                status_code=503,
                content=ErrorResponse(
                    code="controller_heartbeat_lost",
                    message="The synthetic controller heartbeat is unavailable.",
                ).model_dump(mode="json"),
            )

    @application.post(
        "/api/v1/runs/{run_id}/control-simulations",
        response_model=ControlSimulationResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["ot-security"],
        summary="Validate and persist a simulated Modbus site-power command",
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def create_control_simulation(
        run_id: UUID,
        request: ControlSimulationCreateRequest,
        session: SessionDependency,
        principal: OperatorPrincipal,
        control_key: Annotated[
            str | None,
            Header(alias="X-Control-Key", min_length=1, max_length=256),
        ] = None,
    ):
        try:
            authenticate_control_key(control_key, application.state.control_api_key)
            return ControlSimulationRepository(
                session,
                application.state.input_registry,
            ).create(
                run_id,
                interval_index=request.interval_index,
                requested_by=principal.subject,
            )
        except ControlAuthenticationError as exc:
            disabled = not application.state.control_api_key
            return JSONResponse(
                status_code=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                    if disabled
                    else status.HTTP_401_UNAUTHORIZED
                ),
                content=ErrorResponse(
                    code=(
                        "control_simulation_disabled"
                        if disabled
                        else "control_authentication_failed"
                    ),
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="run_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except ControlPolicyError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=ControlPolicyRejectionResponse(
                    message=str(exc),
                    failed_check=exc.failed_check,
                ).model_dump(mode="json"),
            )

    @application.get(
        "/api/v1/runs/{run_id}/control-simulations",
        response_model=ControlSimulationListResponse,
        tags=["ot-security"],
        summary="List persisted simulated control actions for a run",
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def list_control_simulations(
        run_id: UUID,
        session: SessionDependency,
        _principal: AnyPrincipal,
        control_key: Annotated[
            str | None,
            Header(alias="X-Control-Key", min_length=1, max_length=256),
        ] = None,
    ):
        try:
            authenticate_control_key(control_key, application.state.control_api_key)
            return ControlSimulationListResponse(
                items=ControlSimulationRepository(
                    session,
                    application.state.input_registry,
                ).list(run_id)
            )
        except ControlAuthenticationError as exc:
            disabled = not application.state.control_api_key
            return JSONResponse(
                status_code=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                    if disabled
                    else status.HTTP_401_UNAUTHORIZED
                ),
                content=ErrorResponse(
                    code=(
                        "control_simulation_disabled"
                        if disabled
                        else "control_authentication_failed"
                    ),
                    message=str(exc),
                ).model_dump(mode="json"),
            )
        except RunNotFoundError as exc:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    code="run_not_found",
                    message=str(exc),
                ).model_dump(mode="json"),
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
    def cancel_run(
        run_id: UUID, session: SessionDependency, principal: OperatorPrincipal
    ):
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
