from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socketserver
import struct
import threading
from datetime import datetime, timezone

from .modbus_tcp import (
    ALARM_INVALID_WRITE,
    ALARM_NONE,
    ALARM_SAFE_STATE,
    ALARM_STATE_REGISTER,
    ALARM_UNAUTHORIZED_SOURCE,
    COMMAND_MODE_DISPATCH,
    COMMAND_MODE_REGISTER,
    COMMAND_MODE_SAFE_STATE,
    CONTROLLER_ACTIVE,
    CONTROLLER_READY,
    CONTROLLER_SAFE_STATE,
    CONTROLLER_STATE_REGISTER,
    HEARTBEAT_REGISTER,
    MEASURED_SITE_POWER_REGISTER,
    MODBUS_READ_HOLDING_REGISTERS,
    MODBUS_WRITE_MULTIPLE_REGISTERS,
    POWER_SCALE_KW,
    SITE_EXPORT_SETPOINT_REGISTER,
    SITE_IMPORT_SETPOINT_REGISTER,
    decode_request,
    encode_exception_response,
    encode_read_response,
    encode_write_response,
    measured_power_register,
    receive_exact,
)


def _json_event(event_type: str, **details) -> None:
    print(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "component": "synthetic-plc",
                "event_type": event_type,
                **details,
            },
            sort_keys=True,
        ),
        flush=True,
    )


class SimulatedSiteController:
    """Small deterministic PLC model; it has no physical I/O implementation."""

    def __init__(
        self,
        *,
        site_capacity_kw: float = 6400.0,
        allowed_peer_cidrs: tuple[str, ...] = ("127.0.0.0/8",),
        heartbeat_enabled: bool = True,
    ):
        self.site_capacity_kw = float(site_capacity_kw)
        self.heartbeat_enabled = heartbeat_enabled
        self.allowed_peer_networks = tuple(
            ipaddress.ip_network(value) for value in allowed_peer_cidrs
        )
        self._lock = threading.Lock()
        self.registers: dict[int, int] = {
            SITE_IMPORT_SETPOINT_REGISTER: 0,
            SITE_EXPORT_SETPOINT_REGISTER: 0,
            COMMAND_MODE_REGISTER: COMMAND_MODE_DISPATCH,
            MEASURED_SITE_POWER_REGISTER: 0,
            CONTROLLER_STATE_REGISTER: CONTROLLER_READY,
            ALARM_STATE_REGISTER: ALARM_NONE,
            HEARTBEAT_REGISTER: 0,
        }

    def peer_allowed(self, peer_ip: str) -> bool:
        address = ipaddress.ip_address(peer_ip)
        return any(address in network for network in self.allowed_peer_networks)

    def handle_request(self, frame: bytes, *, peer_ip: str) -> bytes | None:
        try:
            transaction_id, unit_id, function, payload = decode_request(frame)
        except Exception as exc:
            _json_event("malformed_modbus_request", peer_ip=peer_ip, reason=str(exc))
            return None
        if not self.peer_allowed(peer_ip):
            with self._lock:
                self.registers[ALARM_STATE_REGISTER] |= ALARM_UNAUTHORIZED_SOURCE
            _json_event(
                "direct_plc_access_rejected",
                peer_ip=peer_ip,
                transaction_id=transaction_id,
            )
            return encode_exception_response(
                function, 0x01, transaction_id=transaction_id, unit_id=unit_id
            )
        if unit_id != 1:
            return encode_exception_response(
                function, 0x0B, transaction_id=transaction_id, unit_id=unit_id
            )
        with self._lock:
            if self.heartbeat_enabled:
                self.registers[HEARTBEAT_REGISTER] = (
                    self.registers[HEARTBEAT_REGISTER] + 1
                ) & 0xFFFF
            if function == MODBUS_WRITE_MULTIPLE_REGISTERS:
                return self._handle_write(
                    transaction_id=transaction_id, unit_id=unit_id, payload=payload
                )
            if function == MODBUS_READ_HOLDING_REGISTERS:
                return self._handle_read(
                    transaction_id=transaction_id, unit_id=unit_id, payload=payload
                )
        return encode_exception_response(
            function, 0x01, transaction_id=transaction_id, unit_id=unit_id
        )

    def _handle_write(
        self, *, transaction_id: int, unit_id: int, payload: bytes
    ) -> bytes:
        if len(payload) != 11:
            return self._invalid_write(transaction_id, unit_id, exception_code=0x03)
        address, quantity, byte_count, import_raw, export_raw, command_mode = struct.unpack(
            ">HHBHHH", payload
        )
        if (
            address != SITE_IMPORT_SETPOINT_REGISTER
            or quantity != 3
            or byte_count != 6
        ):
            return self._invalid_write(transaction_id, unit_id, exception_code=0x02)
        import_kw = import_raw * POWER_SCALE_KW
        export_kw = export_raw * POWER_SCALE_KW
        if (
            (import_raw and export_raw)
            or max(import_kw, export_kw) > self.site_capacity_kw
            or command_mode not in (COMMAND_MODE_DISPATCH, COMMAND_MODE_SAFE_STATE)
            or (command_mode == COMMAND_MODE_SAFE_STATE and (import_raw or export_raw))
        ):
            return self._invalid_write(transaction_id, unit_id, exception_code=0x03)
        setpoint_kw = import_kw - export_kw
        self.registers[SITE_IMPORT_SETPOINT_REGISTER] = import_raw
        self.registers[SITE_EXPORT_SETPOINT_REGISTER] = export_raw
        self.registers[COMMAND_MODE_REGISTER] = command_mode
        self.registers[MEASURED_SITE_POWER_REGISTER] = measured_power_register(setpoint_kw)
        if command_mode == COMMAND_MODE_SAFE_STATE:
            self.registers[CONTROLLER_STATE_REGISTER] = CONTROLLER_SAFE_STATE
            self.registers[ALARM_STATE_REGISTER] = ALARM_SAFE_STATE
            event_type = "emergency_safe_state_activated"
        else:
            self.registers[CONTROLLER_STATE_REGISTER] = CONTROLLER_ACTIVE
            self.registers[ALARM_STATE_REGISTER] = ALARM_NONE
            event_type = "dispatch_setpoint_applied"
        _json_event(
            event_type,
            transaction_id=transaction_id,
            setpoint_kw=setpoint_kw,
            simulated_only=True,
        )
        return encode_write_response(
            transaction_id=transaction_id,
            unit_id=unit_id,
            start_address=address,
            quantity=quantity,
        )

    def _invalid_write(
        self, transaction_id: int, unit_id: int, *, exception_code: int
    ) -> bytes:
        self.registers[ALARM_STATE_REGISTER] |= ALARM_INVALID_WRITE
        _json_event(
            "unsafe_register_write_rejected",
            transaction_id=transaction_id,
            exception_code=exception_code,
        )
        return encode_exception_response(
            MODBUS_WRITE_MULTIPLE_REGISTERS,
            exception_code,
            transaction_id=transaction_id,
            unit_id=unit_id,
        )

    def _handle_read(
        self, *, transaction_id: int, unit_id: int, payload: bytes
    ) -> bytes:
        if len(payload) != 4:
            return encode_exception_response(
                MODBUS_READ_HOLDING_REGISTERS,
                0x03,
                transaction_id=transaction_id,
                unit_id=unit_id,
            )
        address, quantity = struct.unpack(">HH", payload)
        if quantity < 1 or quantity > 125 or address + quantity > 65536:
            return encode_exception_response(
                MODBUS_READ_HOLDING_REGISTERS,
                0x02,
                transaction_id=transaction_id,
                unit_id=unit_id,
            )
        defined = set(self.registers)
        requested = {address + offset for offset in range(quantity)}
        snapshot_range = (
            address == SITE_IMPORT_SETPOINT_REGISTER
            and quantity == HEARTBEAT_REGISTER - SITE_IMPORT_SETPOINT_REGISTER + 1
        )
        if not snapshot_range and not requested.issubset(defined):
            self.registers[ALARM_STATE_REGISTER] |= ALARM_UNAUTHORIZED_SOURCE
            _json_event(
                "register_scan_rejected",
                transaction_id=transaction_id,
                start_address=address,
                quantity=quantity,
            )
            return encode_exception_response(
                MODBUS_READ_HOLDING_REGISTERS,
                0x02,
                transaction_id=transaction_id,
                unit_id=unit_id,
            )
        values = [self.registers.get(address + offset, 0) for offset in range(quantity)]
        return encode_read_response(
            values, transaction_id=transaction_id, unit_id=unit_id
        )


class _ControllerTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, controller: SimulatedSiteController):
        self.controller = controller
        super().__init__(address, _ControllerHandler)


class _ControllerHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(2.0)
        try:
            header = receive_exact(self.request, 7)
            _, protocol_id, length, _ = struct.unpack(">HHHB", header)
            if protocol_id != 0 or not 2 <= length <= 254:
                return
            frame = header + receive_exact(self.request, length - 1)
            response = self.server.controller.handle_request(
                frame, peer_ip=self.client_address[0]
            )
            if response:
                self.request.sendall(response)
        except (OSError, ValueError):
            return


class SimulatedPLCServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        controller: SimulatedSiteController | None = None,
    ):
        self.controller = controller or SimulatedSiteController()
        self.server = _ControllerTCPServer((host, port), self.controller)
        self.thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.server.server_address[:2]
        return str(host), int(port)

    def start(self) -> "SimulatedPLCServer":
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join(timeout=2)

    def __enter__(self) -> "SimulatedPLCServer":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the synthetic DepotFlux Modbus/TCP PLC.")
    parser.add_argument("--host", default=os.environ.get("DEMO_PLC_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DEMO_PLC_PORT", "1502")))
    parser.add_argument(
        "--site-capacity-kw",
        type=float,
        default=float(os.environ.get("DEMO_PLC_SITE_CAPACITY_KW", "6400")),
    )
    args = parser.parse_args(argv)
    cidrs = tuple(
        item.strip()
        for item in os.environ.get("DEMO_PLC_ALLOWED_CIDRS", "127.0.0.0/8").split(",")
        if item.strip()
    )
    controller = SimulatedSiteController(
        site_capacity_kw=args.site_capacity_kw,
        allowed_peer_cidrs=cidrs,
    )
    server = _ControllerTCPServer((args.host, args.port), controller)
    _json_event(
        "synthetic_plc_started",
        host=args.host,
        port=args.port,
        allowed_peer_cidrs=cidrs,
        simulated_only=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
