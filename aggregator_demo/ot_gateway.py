from __future__ import annotations

import argparse
import json
import math
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from typing import Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .modbus_tcp import (
    CONTROLLER_ACTIVE,
    CONTROLLER_READY,
    CONTROLLER_SAFE_STATE,
    ModbusProtocolError,
    ModbusTcpClient,
    ModbusTransportError,
    MAX_UNSIGNED_POWER_KW,
)
from .pymodbus_tcp import PymodbusTcpClient


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_event(event_type: str, *, correlation_id: UUID | None, **details) -> None:
    print(
        json.dumps(
            {
                "timestamp": utc_now().isoformat(),
                "component": "ot-gateway",
                "event_type": event_type,
                "correlation_id": str(correlation_id) if correlation_id else None,
                **details,
            },
            sort_keys=True,
        ),
        flush=True,
    )


class GatewayPolicyError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GatewayUnavailableError(ConnectionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GatewayDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID
    correlation_id: UUID
    issued_at: datetime
    expires_at: datetime
    setpoint_kw: float
    site_capacity_kw: float = Field(gt=0)
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("gateway timestamps must include a timezone")
        return value.astimezone(timezone.utc)


class GatewaySafeStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID
    correlation_id: UUID
    issued_at: datetime
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("gateway timestamps must include a timezone")
        return value.astimezone(timezone.utc)


class GatewayControllerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID
    correlation_id: UUID
    accepted: Literal[True] = True
    action: Literal["dispatch", "safe_state"]
    frame_hex: str
    response_frame_hex: str
    setpoint_kw: float
    import_setpoint_kw: float
    export_setpoint_kw: float
    measured_site_power_kw: float
    controller_state: Literal["ready", "active", "safe_state", "unknown"]
    alarm_state: int = Field(ge=0, le=65535)
    heartbeat: int = Field(ge=0, le=65535)
    transport_attempts: int = Field(ge=1, le=4)
    latency_ms: float = Field(ge=0)
    simulated_only: Literal[True] = True


class GatewayErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


def _state_name(value: int) -> str:
    return {
        CONTROLLER_READY: "ready",
        CONTROLLER_ACTIVE: "active",
        CONTROLLER_SAFE_STATE: "safe_state",
    }.get(value, "unknown")


class DispatchGateway:
    def __init__(
        self,
        client: ModbusTcpClient,
        *,
        maximum_command_age_seconds: float = 30.0,
        maximum_future_skew_seconds: float = 5.0,
        heartbeat_stale_seconds: float = 15.0,
        replay_cache_size: int = 10_000,
        clock=utc_now,
    ):
        self.client = client
        self.maximum_command_age_seconds = maximum_command_age_seconds
        self.maximum_future_skew_seconds = maximum_future_skew_seconds
        self.heartbeat_stale_seconds = heartbeat_stale_seconds
        self.replay_cache_size = replay_cache_size
        self.clock = clock
        self._seen_commands: OrderedDict[UUID, None] = OrderedDict()
        self._lock = threading.Lock()
        self._last_heartbeat: int | None = None
        self._last_heartbeat_change = time.monotonic()

    def dispatch(self, command: GatewayDispatchRequest) -> GatewayControllerResponse:
        started = time.perf_counter()
        self._validate_window(command.issued_at, command.expires_at)
        self._reject_replay(command.command_id, command.correlation_id)
        if not math.isfinite(command.setpoint_kw):
            raise GatewayPolicyError("non_finite_setpoint", "setpoint must be finite")
        if abs(command.setpoint_kw) > min(
            command.site_capacity_kw, MAX_UNSIGNED_POWER_KW
        ) + 1e-7:
            raise GatewayPolicyError(
                "unsafe_setpoint",
                "setpoint exceeds the site-capacity or protocol envelope",
            )
        transaction_id = command.command_id.int & 0xFFFF
        try:
            frame, response, attempts = self.client.write_setpoint(
                command.setpoint_kw,
                transaction_id=transaction_id,
            )
            snapshot = self.client.snapshot(
                transaction_id=(transaction_id + 1) & 0xFFFF
            )
        except (ModbusProtocolError, ModbusTransportError) as exc:
            safe_state_applied = self._best_effort_safe_state(transaction_id)
            _json_event(
                "controller_exchange_failed",
                correlation_id=command.correlation_id,
                command_id=str(command.command_id),
                safe_state_applied=safe_state_applied,
                reason=str(exc),
            )
            raise GatewayUnavailableError(
                "controller_unavailable",
                "synthetic controller exchange failed; a zero-power safe-state was attempted",
            ) from exc
        response_model = GatewayControllerResponse(
            command_id=command.command_id,
            correlation_id=command.correlation_id,
            action="dispatch",
            frame_hex=frame.hex(),
            response_frame_hex=response.hex(),
            setpoint_kw=command.setpoint_kw,
            import_setpoint_kw=snapshot.import_setpoint_kw,
            export_setpoint_kw=snapshot.export_setpoint_kw,
            measured_site_power_kw=snapshot.measured_site_power_kw,
            controller_state=_state_name(snapshot.controller_state),
            alarm_state=snapshot.alarm_state,
            heartbeat=snapshot.heartbeat,
            transport_attempts=attempts,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
        _json_event(
            "dispatch_applied",
            correlation_id=command.correlation_id,
            command_id=str(command.command_id),
            setpoint_kw=command.setpoint_kw,
            controller_state=response_model.controller_state,
            simulated_only=True,
        )
        return response_model

    def safe_state(
        self, request: GatewaySafeStateRequest
    ) -> GatewayControllerResponse:
        started = time.perf_counter()
        self._validate_window(request.issued_at, request.expires_at)
        self._reject_replay(request.command_id, request.correlation_id)
        transaction_id = request.command_id.int & 0xFFFF
        try:
            frame, response, attempts = self.client.write_setpoint(
                0.0, transaction_id=transaction_id, safe_state=True
            )
            snapshot = self.client.snapshot(
                transaction_id=(transaction_id + 1) & 0xFFFF
            )
        except (ModbusProtocolError, ModbusTransportError) as exc:
            raise GatewayUnavailableError(
                "safe_state_unavailable",
                "synthetic controller did not acknowledge the emergency safe-state request",
            ) from exc
        result = GatewayControllerResponse(
            command_id=request.command_id,
            correlation_id=request.correlation_id,
            action="safe_state",
            frame_hex=frame.hex(),
            response_frame_hex=response.hex(),
            setpoint_kw=0.0,
            import_setpoint_kw=snapshot.import_setpoint_kw,
            export_setpoint_kw=snapshot.export_setpoint_kw,
            measured_site_power_kw=snapshot.measured_site_power_kw,
            controller_state=_state_name(snapshot.controller_state),
            alarm_state=snapshot.alarm_state,
            heartbeat=snapshot.heartbeat,
            transport_attempts=attempts,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
        _json_event(
            "emergency_safe_state_activated",
            correlation_id=request.correlation_id,
            command_id=str(request.command_id),
            reason=request.reason,
            simulated_only=True,
        )
        return result

    def controller_status(self) -> dict:
        started = time.perf_counter()
        try:
            snapshot = self.client.snapshot(transaction_id=0xFFFE)
        except (ModbusProtocolError, ModbusTransportError) as exc:
            _json_event(
                "controller_heartbeat_lost",
                correlation_id=None,
                reason=str(exc),
                safe_state_applied=False,
            )
            raise GatewayUnavailableError(
                "controller_heartbeat_lost",
                "synthetic controller heartbeat could not be read",
            ) from exc
        now = time.monotonic()
        if self._last_heartbeat == snapshot.heartbeat:
            if now - self._last_heartbeat_change >= self.heartbeat_stale_seconds:
                safe_state_applied = self._best_effort_safe_state(0xFFFB)
                _json_event(
                    "controller_heartbeat_lost",
                    correlation_id=None,
                    heartbeat=snapshot.heartbeat,
                    safe_state_applied=safe_state_applied,
                )
                raise GatewayUnavailableError(
                    "controller_heartbeat_lost",
                    "synthetic controller heartbeat stopped changing; safe state was attempted",
                )
        else:
            self._last_heartbeat = snapshot.heartbeat
            self._last_heartbeat_change = now
        return {
            "controller_state": _state_name(snapshot.controller_state),
            "alarm_state": snapshot.alarm_state,
            "heartbeat": snapshot.heartbeat,
            "measured_site_power_kw": snapshot.measured_site_power_kw,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "simulated_only": True,
        }

    def _validate_window(self, issued_at: datetime, expires_at: datetime) -> None:
        now = self.clock().astimezone(timezone.utc)
        issued = issued_at.astimezone(timezone.utc)
        expires = expires_at.astimezone(timezone.utc)
        if expires <= issued:
            raise GatewayPolicyError(
                "invalid_command_window", "command expiry must be after issue time"
            )
        if issued > now + timedelta(seconds=self.maximum_future_skew_seconds):
            raise GatewayPolicyError(
                "future_command", "command issue time exceeds the permitted clock skew"
            )
        if (
            now > expires
            or (now - issued).total_seconds() > self.maximum_command_age_seconds
        ):
            raise GatewayPolicyError(
                "stale_command", "command is outside the permitted freshness window"
            )

    def _reject_replay(self, command_id: UUID, correlation_id: UUID) -> None:
        with self._lock:
            if command_id in self._seen_commands:
                _json_event(
                    "replayed_command_rejected",
                    correlation_id=correlation_id,
                    command_id=str(command_id),
                )
                raise GatewayPolicyError(
                    "replayed_command", "command identifier has already been processed"
                )
            self._seen_commands[command_id] = None
            self._seen_commands.move_to_end(command_id)
            while len(self._seen_commands) > self.replay_cache_size:
                self._seen_commands.popitem(last=False)

    def _best_effort_safe_state(self, transaction_id: int) -> bool:
        try:
            self.client.write_setpoint(
                0.0,
                transaction_id=(transaction_id + 2) & 0xFFFF,
                safe_state=True,
            )
            return True
        except (ModbusProtocolError, ModbusTransportError):
            return False


class OTGatewayClient:
    """HTTP client used by the application API to cross the supervisory conduit."""

    def __init__(
        self,
        base_url: str,
        gateway_key: str,
        *,
        timeout_seconds: float = 3.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.gateway_key = gateway_key
        self.timeout_seconds = timeout_seconds

    def dispatch(self, command: GatewayDispatchRequest) -> GatewayControllerResponse:
        return self._post("/internal/v1/dispatch", command)

    def safe_state(
        self, request: GatewaySafeStateRequest
    ) -> GatewayControllerResponse:
        return self._post("/internal/v1/safe-state", request)

    def controller_status(self) -> dict:
        try:
            response = httpx.get(
                f"{self.base_url}/internal/v1/controller",
                headers={"X-Gateway-Key": self.gateway_key},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GatewayUnavailableError(
                "gateway_unavailable", "supervisory gateway is unavailable"
            ) from exc
        if response.status_code >= 400:
            body = response.json()
            raise GatewayUnavailableError(
                str(body.get("code", "gateway_unavailable")),
                str(body.get("message", "supervisory gateway is unavailable")),
            )
        return response.json()

    def _post(self, path: str, payload: BaseModel) -> GatewayControllerResponse:
        try:
            response = httpx.post(
                f"{self.base_url}{path}",
                json=payload.model_dump(mode="json"),
                headers={"X-Gateway-Key": self.gateway_key},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GatewayUnavailableError(
                "gateway_unavailable", "supervisory gateway is unavailable"
            ) from exc
        body = response.json()
        if response.status_code == status.HTTP_409_CONFLICT:
            raise GatewayPolicyError(str(body["code"]), str(body["message"]))
        if response.status_code >= 400:
            raise GatewayUnavailableError(
                str(body.get("code", "gateway_unavailable")),
                str(body.get("message", "supervisory gateway is unavailable")),
            )
        return GatewayControllerResponse.model_validate(body)


def authenticate_gateway_request(
    provided: str | None, configured: str | None
) -> None:
    """Apply the same credential gate used by the internal gateway routes."""
    if not configured or not provided or not compare_digest(provided, configured):
        raise GatewayPolicyError(
            "gateway_authentication_failed", "invalid supervisory gateway credential"
        )


def create_gateway_app(
    *,
    gateway: DispatchGateway | None = None,
    gateway_key: str | None = None,
) -> FastAPI:
    if gateway is None:
        client_type = (
            PymodbusTcpClient
            if os.environ.get("DEMO_MODBUS_DRIVER", "pymodbus").lower() == "pymodbus"
            else ModbusTcpClient
        )
        client = client_type(
            os.environ.get("DEMO_PLC_HOST", "plc-simulator"),
            int(os.environ.get("DEMO_PLC_PORT", "1502")),
            timeout_seconds=float(os.environ.get("DEMO_PLC_TIMEOUT_SECONDS", "1")),
            retries=int(os.environ.get("DEMO_PLC_RETRIES", "2")),
        )
        gateway = DispatchGateway(
            client,
            heartbeat_stale_seconds=float(
                os.environ.get("DEMO_HEARTBEAT_STALE_SECONDS", "15")
            ),
        )
    configured_key = gateway_key or os.environ.get("DEMO_GATEWAY_API_KEY")
    application = FastAPI(
        title="DepotFlux Synthetic OT Gateway",
        description="Internal-only gateway for a synthetic Modbus/TCP controller.",
        version="0.1.0",
    )

    @application.get("/health/live")
    def live() -> dict:
        return {"service": "depotflux-ot-gateway", "status": "ok"}

    @application.get("/health/ready")
    def ready(response: Response) -> dict:
        try:
            controller = gateway.controller_status()
            return {"service": "depotflux-ot-gateway", "status": "ok", **controller}
        except GatewayUnavailableError as exc:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "service": "depotflux-ot-gateway",
                "status": "unavailable",
                "code": exc.code,
            }

    @application.post(
        "/internal/v1/dispatch", response_model=GatewayControllerResponse
    )
    def dispatch(
        request: GatewayDispatchRequest,
        gateway_header: str | None = Header(default=None, alias="X-Gateway-Key"),
    ):
        try:
            authenticate_gateway_request(gateway_header, configured_key)
        except GatewayPolicyError as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=GatewayErrorResponse(code=exc.code, message=str(exc)).model_dump(),
            )
        try:
            return gateway.dispatch(request)
        except GatewayPolicyError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=GatewayErrorResponse(code=exc.code, message=str(exc)).model_dump(),
            )
        except GatewayUnavailableError as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=GatewayErrorResponse(code=exc.code, message=str(exc)).model_dump(),
            )

    @application.post(
        "/internal/v1/safe-state", response_model=GatewayControllerResponse
    )
    def safe_state(
        request: GatewaySafeStateRequest,
        gateway_header: str | None = Header(default=None, alias="X-Gateway-Key"),
    ):
        try:
            authenticate_gateway_request(gateway_header, configured_key)
        except GatewayPolicyError as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=GatewayErrorResponse(code=exc.code, message=str(exc)).model_dump(),
            )
        try:
            return gateway.safe_state(request)
        except GatewayPolicyError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=GatewayErrorResponse(code=exc.code, message=str(exc)).model_dump(),
            )
        except GatewayUnavailableError as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=GatewayErrorResponse(code=exc.code, message=str(exc)).model_dump(),
            )

    @application.get("/internal/v1/controller")
    def controller(
        gateway_header: str | None = Header(default=None, alias="X-Gateway-Key"),
    ):
        try:
            authenticate_gateway_request(gateway_header, configured_key)
            return gateway.controller_status()
        except GatewayPolicyError as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=GatewayErrorResponse(code=exc.code, message=str(exc)).model_dump(),
            )
        except GatewayUnavailableError as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=GatewayErrorResponse(code=exc.code, message=str(exc)).model_dump(),
            )

    return application


app = create_gateway_app()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the synthetic DepotFlux OT gateway.")
    parser.add_argument("--host", default=os.environ.get("DEMO_GATEWAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DEMO_GATEWAY_PORT", "8081")))
    args = parser.parse_args(argv)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
