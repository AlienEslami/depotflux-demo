from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aggregator_demo.modbus_tcp import (
    CONTROLLER_ACTIVE,
    SITE_EXPORT_SETPOINT_REGISTER,
    SITE_IMPORT_SETPOINT_REGISTER,
)
from aggregator_demo.ot_gateway import (
    DispatchGateway,
    GatewayDispatchRequest,
    create_gateway_app,
)
from aggregator_demo.plc_simulator import SimulatedPLCServer, SimulatedSiteController
from aggregator_demo.pymodbus_tcp import PymodbusTcpClient


class _CountingController(SimulatedSiteController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.modbus_request_count = 0

    def handle_request(self, frame: bytes, *, peer_ip: str) -> bytes | None:
        self.modbus_request_count += 1
        return super().handle_request(frame, peer_ip=peer_ip)


def _dispatch_payload(setpoint_kw: float, *, site_capacity_kw: float = 100.0) -> dict:
    issued_at = datetime.now(timezone.utc)
    return GatewayDispatchRequest(
        command_id=uuid4(),
        correlation_id=uuid4(),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=20),
        setpoint_kw=setpoint_kw,
        site_capacity_kw=site_capacity_kw,
        result_sha256="a" * 64,
    ).model_dump(mode="json")


def test_pymodbus_client_writes_and_reads_real_tcp_telemetry():
    controller = SimulatedSiteController(site_capacity_kw=100.0)
    with SimulatedPLCServer(controller=controller) as server:
        client = PymodbusTcpClient(*server.address, retries=0)

        request, response, attempts = client.write_setpoint(
            42.3, transaction_id=17
        )
        snapshot = client.snapshot(transaction_id=18)

    assert request.hex()
    assert response.hex()
    assert attempts == 1
    assert snapshot.import_setpoint_kw == pytest.approx(42.3)
    assert snapshot.measured_site_power_kw == pytest.approx(42.3)
    assert snapshot.controller_state == CONTROLLER_ACTIVE


def test_gateway_rejects_unauthorized_and_unsafe_setpoints_without_modbus_transmission():
    controller = _CountingController(site_capacity_kw=100.0)
    with SimulatedPLCServer(controller=controller) as server:
        gateway = DispatchGateway(PymodbusTcpClient(*server.address, retries=0))
        client = TestClient(
            create_gateway_app(gateway=gateway, gateway_key="trusted-gridtwin-key")
        )

        unauthorized = client.post(
            "/internal/v1/dispatch",
            headers={"X-Gateway-Key": "unauthorized-gridtwin-key"},
            json=_dispatch_payload(42.3),
        )
        unsafe = client.post(
            "/internal/v1/dispatch",
            headers={"X-Gateway-Key": "trusted-gridtwin-key"},
            json=_dispatch_payload(100.1),
        )

    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "gateway_authentication_failed"
    assert unsafe.status_code == 409
    assert unsafe.json()["code"] == "unsafe_setpoint"
    assert controller.modbus_request_count == 0
    assert controller.registers[SITE_IMPORT_SETPOINT_REGISTER] == 0
    assert controller.registers[SITE_EXPORT_SETPOINT_REGISTER] == 0
