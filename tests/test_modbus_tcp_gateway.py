from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from aggregator_demo.modbus_tcp import (
    ALARM_SAFE_STATE,
    COMMAND_MODE_DISPATCH,
    COMMAND_MODE_REGISTER,
    CONTROLLER_ACTIVE,
    CONTROLLER_SAFE_STATE,
    ModbusProtocolError,
    ModbusTcpClient,
    encode_read_request,
    decode_dispatch_request,
    encode_dispatch_request,
)
from aggregator_demo.ot_gateway import (
    DispatchGateway,
    GatewayDispatchRequest,
    GatewayPolicyError,
    GatewaySafeStateRequest,
    GatewayUnavailableError,
)
from aggregator_demo.plc_simulator import SimulatedPLCServer, SimulatedSiteController


def _command(*, issued_at: datetime | None = None, setpoint_kw: float = 42.3):
    now = datetime.now(timezone.utc)
    return GatewayDispatchRequest(
        command_id=uuid4(),
        correlation_id=uuid4(),
        issued_at=issued_at or now,
        expires_at=(issued_at or now) + timedelta(seconds=20),
        setpoint_kw=setpoint_kw,
        site_capacity_kw=100.0,
        result_sha256="a" * 64,
    )


def test_three_register_command_frame_distinguishes_zero_dispatch_from_safe_state():
    ordinary = decode_dispatch_request(encode_dispatch_request(0.0, transaction_id=7))
    safe = decode_dispatch_request(
        encode_dispatch_request(0.0, transaction_id=8, safe_state=True)
    )

    assert ordinary["setpoint_kw"] == 0.0
    assert ordinary["safe_state"] is False
    assert safe["safe_state"] is True
    with pytest.raises(ModbusProtocolError):
        decode_dispatch_request(
            encode_dispatch_request(1.0, transaction_id=9, safe_state=True)
        )


def test_actual_modbus_tcp_round_trip_and_emergency_safe_state():
    controller = SimulatedSiteController(site_capacity_kw=100.0)
    with SimulatedPLCServer(controller=controller) as server:
        client = ModbusTcpClient(*server.address, retries=0)
        gateway = DispatchGateway(client)

        applied = gateway.dispatch(_command(setpoint_kw=-42.3))
        assert applied.import_setpoint_kw == 0.0
        assert applied.export_setpoint_kw == pytest.approx(42.3)
        assert applied.measured_site_power_kw == pytest.approx(-42.3)
        assert applied.controller_state == "active"

        zero = gateway.dispatch(_command(setpoint_kw=0.0))
        assert zero.controller_state == "active"
        assert controller.registers[COMMAND_MODE_REGISTER] == COMMAND_MODE_DISPATCH
        assert controller.registers[120] == CONTROLLER_ACTIVE

        now = datetime.now(timezone.utc)
        safe = gateway.safe_state(
            GatewaySafeStateRequest(
                command_id=uuid4(),
                correlation_id=uuid4(),
                issued_at=now,
                expires_at=now + timedelta(seconds=20),
                reason="operator drill",
            )
        )
        assert safe.controller_state == "safe_state"
        assert controller.registers[120] == CONTROLLER_SAFE_STATE
        assert controller.registers[121] == ALARM_SAFE_STATE


def test_gateway_rejects_replay_stale_and_out_of_range_before_transport():
    controller = SimulatedSiteController(site_capacity_kw=100.0)
    with SimulatedPLCServer(controller=controller) as server:
        gateway = DispatchGateway(ModbusTcpClient(*server.address, retries=0))
        command = _command()
        gateway.dispatch(command)

        with pytest.raises(GatewayPolicyError, match="already been processed") as replay:
            gateway.dispatch(command)
        assert replay.value.code == "replayed_command"

        stale_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        with pytest.raises(GatewayPolicyError, match="freshness") as stale:
            gateway.dispatch(_command(issued_at=stale_time))
        assert stale.value.code == "stale_command"

        with pytest.raises(GatewayPolicyError, match="capacity") as unsafe:
            gateway.dispatch(_command(setpoint_kw=100.1))
        assert unsafe.value.code == "unsafe_setpoint"

        protocol_unsafe = _command(setpoint_kw=7000.0)
        protocol_unsafe.site_capacity_kw = 8000.0
        with pytest.raises(GatewayPolicyError, match="protocol envelope"):
            gateway.dispatch(protocol_unsafe)


def test_plc_rejects_non_gateway_peer_and_sets_alarm():
    controller = SimulatedSiteController(allowed_peer_cidrs=("192.0.2.10/32",))
    response = controller.handle_request(
        encode_dispatch_request(10.0, transaction_id=5), peer_ip="198.51.100.9"
    )

    assert response is not None
    assert response[7] == 0x90
    assert controller.registers[121] != 0


def test_register_scan_is_detected_and_rejected():
    controller = SimulatedSiteController()
    response = controller.handle_request(
        encode_read_request(0, 125, transaction_id=44), peer_ip="127.0.0.1"
    )

    assert response is not None
    assert response[7] == 0x83
    assert controller.registers[121] != 0


def test_frozen_heartbeat_triggers_safe_state():
    controller = SimulatedSiteController(heartbeat_enabled=False)
    with SimulatedPLCServer(controller=controller) as server:
        gateway = DispatchGateway(
            ModbusTcpClient(*server.address, retries=0), heartbeat_stale_seconds=0
        )
        assert gateway.controller_status()["heartbeat"] == 0

        with pytest.raises(GatewayUnavailableError, match="heartbeat stopped changing"):
            gateway.controller_status()
        assert controller.registers[120] == CONTROLLER_SAFE_STATE


def test_unreachable_controller_uses_bounded_attempts_and_reports_unknown_state():
    server = SimulatedPLCServer().start()
    host, port = server.address
    server.close()
    gateway = DispatchGateway(
        ModbusTcpClient(host, port, timeout_seconds=0.05, retries=0)
    )

    with pytest.raises(GatewayUnavailableError, match="zero-power safe-state was attempted"):
        gateway.dispatch(_command())
