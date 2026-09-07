from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass


MODBUS_READ_HOLDING_REGISTERS = 0x03
MODBUS_WRITE_MULTIPLE_REGISTERS = 0x10

SITE_IMPORT_SETPOINT_REGISTER = 100
SITE_EXPORT_SETPOINT_REGISTER = 101
COMMAND_MODE_REGISTER = 102
MEASURED_SITE_POWER_REGISTER = 110
CONTROLLER_STATE_REGISTER = 120
ALARM_STATE_REGISTER = 121
HEARTBEAT_REGISTER = 130

POWER_SCALE_KW = 0.1
MAX_UNSIGNED_POWER_KW = 0xFFFF * POWER_SCALE_KW
CONTROLLER_READY = 1
CONTROLLER_ACTIVE = 2
CONTROLLER_SAFE_STATE = 3

ALARM_NONE = 0
ALARM_SAFE_STATE = 1 << 0
ALARM_INVALID_WRITE = 1 << 1
ALARM_HEARTBEAT_LOST = 1 << 2
ALARM_UNAUTHORIZED_SOURCE = 1 << 3

COMMAND_MODE_DISPATCH = 0
COMMAND_MODE_SAFE_STATE = 1


class ModbusProtocolError(RuntimeError):
    pass


class ModbusTransportError(ConnectionError):
    pass


@dataclass(frozen=True)
class ControllerSnapshot:
    import_setpoint_kw: float
    export_setpoint_kw: float
    measured_site_power_kw: float
    controller_state: int
    alarm_state: int
    heartbeat: int


def _unsigned_register(value: float, *, scale_kw: float = POWER_SCALE_KW) -> int:
    scaled = int(round(float(value) / scale_kw))
    if not 0 <= scaled <= 0xFFFF:
        raise ModbusProtocolError("power value cannot be represented as an unsigned register")
    return scaled


def _signed_register(value: float, *, scale_kw: float = POWER_SCALE_KW) -> int:
    scaled = int(round(float(value) / scale_kw))
    if not -32768 <= scaled <= 32767:
        raise ModbusProtocolError("power value cannot be represented as a signed register")
    return scaled & 0xFFFF


def signed_register_value(raw: int, *, scale_kw: float = POWER_SCALE_KW) -> float:
    signed = raw - 65536 if raw >= 32768 else raw
    return signed * scale_kw


def encode_dispatch_request(
    setpoint_kw: float,
    *,
    transaction_id: int,
    unit_id: int = 1,
    safe_state: bool = False,
) -> bytes:
    """Encode a site command without allowing import and export simultaneously."""
    if not 0 <= transaction_id <= 0xFFFF:
        raise ModbusProtocolError("transaction ID is outside uint16 range")
    if not 1 <= unit_id <= 247:
        raise ModbusProtocolError("unit ID is outside the Modbus device range")
    import_kw = max(float(setpoint_kw), 0.0)
    export_kw = max(-float(setpoint_kw), 0.0)
    values = (
        _unsigned_register(import_kw),
        _unsigned_register(export_kw),
        COMMAND_MODE_SAFE_STATE if safe_state else COMMAND_MODE_DISPATCH,
    )
    pdu = struct.pack(
        ">BHHBHHH",
        MODBUS_WRITE_MULTIPLE_REGISTERS,
        SITE_IMPORT_SETPOINT_REGISTER,
        len(values),
        len(values) * 2,
        *values,
    )
    return struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu


def decode_dispatch_request(frame: bytes) -> dict:
    transaction_id, unit_id, function, payload = decode_request(frame)
    if function != MODBUS_WRITE_MULTIPLE_REGISTERS or len(payload) != 11:
        raise ModbusProtocolError("frame is not a three-register command write")
    address, quantity, byte_count, import_raw, export_raw, command_mode = struct.unpack(
        ">HHBHHH", payload
    )
    if (
        address != SITE_IMPORT_SETPOINT_REGISTER
        or quantity != 3
        or byte_count != 6
    ):
        raise ModbusProtocolError("command frame does not target the defined register block")
    import_kw = import_raw * POWER_SCALE_KW
    export_kw = export_raw * POWER_SCALE_KW
    if import_kw and export_kw:
        raise ModbusProtocolError("import and export registers cannot both be non-zero")
    if command_mode not in (COMMAND_MODE_DISPATCH, COMMAND_MODE_SAFE_STATE):
        raise ModbusProtocolError("command mode is not recognized")
    if command_mode == COMMAND_MODE_SAFE_STATE and (import_kw or export_kw):
        raise ModbusProtocolError("safe-state commands must request zero power")
    return {
        "transaction_id": transaction_id,
        "unit_id": unit_id,
        "import_setpoint_kw": import_kw,
        "export_setpoint_kw": export_kw,
        "setpoint_kw": import_kw - export_kw,
        "safe_state": command_mode == COMMAND_MODE_SAFE_STATE,
    }


def encode_read_request(
    start_address: int,
    quantity: int,
    *,
    transaction_id: int,
    unit_id: int = 1,
) -> bytes:
    if not 0 <= start_address <= 0xFFFF or not 1 <= quantity <= 125:
        raise ModbusProtocolError("invalid holding-register read range")
    pdu = struct.pack(">BHH", MODBUS_READ_HOLDING_REGISTERS, start_address, quantity)
    return struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu


def decode_request(frame: bytes) -> tuple[int, int, int, bytes]:
    if len(frame) < 8:
        raise ModbusProtocolError("Modbus/TCP request is shorter than the MBAP header")
    transaction_id, protocol_id, length, unit_id = struct.unpack(">HHHB", frame[:7])
    if protocol_id != 0 or length != len(frame) - 6:
        raise ModbusProtocolError("invalid Modbus/TCP MBAP header")
    return transaction_id, unit_id, frame[7], frame[8:]


def encode_write_response(
    *, transaction_id: int, unit_id: int, start_address: int, quantity: int
) -> bytes:
    pdu = struct.pack(">BHH", MODBUS_WRITE_MULTIPLE_REGISTERS, start_address, quantity)
    return struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu


def encode_read_response(
    values: list[int], *, transaction_id: int, unit_id: int
) -> bytes:
    pdu = struct.pack(">BB", MODBUS_READ_HOLDING_REGISTERS, len(values) * 2)
    pdu += struct.pack(f">{len(values)}H", *values)
    return struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu


def encode_exception_response(
    function: int, exception_code: int, *, transaction_id: int, unit_id: int
) -> bytes:
    pdu = struct.pack(">BB", function | 0x80, exception_code)
    return struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu


def decode_write_response(
    frame: bytes, *, expected_transaction_id: int, expected_unit_id: int = 1
) -> None:
    transaction_id, unit_id, function, payload = decode_request(frame)
    _raise_for_exception(function, payload)
    if transaction_id != expected_transaction_id or unit_id != expected_unit_id:
        raise ModbusProtocolError("write response does not match the request")
    if function != MODBUS_WRITE_MULTIPLE_REGISTERS or len(payload) != 4:
        raise ModbusProtocolError("unexpected write response")
    address, quantity = struct.unpack(">HH", payload)
    if address != SITE_IMPORT_SETPOINT_REGISTER or quantity != 3:
        raise ModbusProtocolError("write response acknowledges an unexpected register range")


def decode_read_response(
    frame: bytes,
    *,
    expected_transaction_id: int,
    expected_quantity: int,
    expected_unit_id: int = 1,
) -> list[int]:
    transaction_id, unit_id, function, payload = decode_request(frame)
    _raise_for_exception(function, payload)
    if transaction_id != expected_transaction_id or unit_id != expected_unit_id:
        raise ModbusProtocolError("read response does not match the request")
    if function != MODBUS_READ_HOLDING_REGISTERS or not payload:
        raise ModbusProtocolError("unexpected read response")
    byte_count = payload[0]
    if byte_count != expected_quantity * 2 or len(payload[1:]) != byte_count:
        raise ModbusProtocolError("read response contains an invalid register count")
    return list(struct.unpack(f">{expected_quantity}H", payload[1:]))


def _raise_for_exception(function: int, payload: bytes) -> None:
    if function & 0x80:
        code = payload[0] if payload else 0
        raise ModbusProtocolError(f"controller returned Modbus exception {code}")


def receive_frame(stream: socket.socket) -> bytes:
    header = receive_exact(stream, 7)
    if not header:
        raise ModbusTransportError("controller closed the connection")
    _, protocol_id, length, _ = struct.unpack(">HHHB", header)
    if protocol_id != 0 or not 2 <= length <= 254:
        raise ModbusProtocolError("invalid Modbus/TCP response header")
    return header + receive_exact(stream, length - 1)


def receive_exact(stream: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        block = stream.recv(size - len(chunks))
        if not block:
            raise ModbusTransportError("connection closed before the frame completed")
        chunks.extend(block)
    return bytes(chunks)


class ModbusTcpClient:
    def __init__(
        self,
        host: str,
        port: int = 1502,
        *,
        timeout_seconds: float = 1.0,
        retries: int = 2,
        retry_delay_seconds: float = 0.05,
    ):
        if not 0 <= retries <= 3:
            raise ValueError("retries must be between zero and three")
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.retry_delay_seconds = retry_delay_seconds

    def exchange(self, frame: bytes) -> tuple[bytes, int]:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            try:
                with socket.create_connection(
                    (self.host, self.port), timeout=self.timeout_seconds
                ) as stream:
                    stream.settimeout(self.timeout_seconds)
                    stream.sendall(frame)
                    return receive_frame(stream), attempt
            except (OSError, ModbusProtocolError, ModbusTransportError) as exc:
                last_error = exc
                if attempt <= self.retries:
                    time.sleep(self.retry_delay_seconds)
        raise ModbusTransportError(
            f"controller exchange failed after {self.retries + 1} attempts: {last_error}"
        ) from last_error

    def write_setpoint(
        self, setpoint_kw: float, *, transaction_id: int, safe_state: bool = False
    ) -> tuple[bytes, bytes, int]:
        request = encode_dispatch_request(
            setpoint_kw,
            transaction_id=transaction_id,
            safe_state=safe_state,
        )
        response, attempts = self.exchange(request)
        decode_write_response(response, expected_transaction_id=transaction_id)
        return request, response, attempts

    def read_registers(
        self, start_address: int, quantity: int, *, transaction_id: int
    ) -> tuple[list[int], bytes, bytes, int]:
        request = encode_read_request(
            start_address, quantity, transaction_id=transaction_id
        )
        response, attempts = self.exchange(request)
        values = decode_read_response(
            response,
            expected_transaction_id=transaction_id,
            expected_quantity=quantity,
        )
        return values, request, response, attempts

    def snapshot(self, *, transaction_id: int) -> ControllerSnapshot:
        values, _, _, _ = self.read_registers(
            SITE_IMPORT_SETPOINT_REGISTER,
            HEARTBEAT_REGISTER - SITE_IMPORT_SETPOINT_REGISTER + 1,
            transaction_id=transaction_id,
        )
        return ControllerSnapshot(
            import_setpoint_kw=values[0] * POWER_SCALE_KW,
            export_setpoint_kw=values[1] * POWER_SCALE_KW,
            measured_site_power_kw=signed_register_value(
                values[MEASURED_SITE_POWER_REGISTER - SITE_IMPORT_SETPOINT_REGISTER]
            ),
            controller_state=values[
                CONTROLLER_STATE_REGISTER - SITE_IMPORT_SETPOINT_REGISTER
            ],
            alarm_state=values[ALARM_STATE_REGISTER - SITE_IMPORT_SETPOINT_REGISTER],
            heartbeat=values[HEARTBEAT_REGISTER - SITE_IMPORT_SETPOINT_REGISTER],
        )


def measured_power_register(value_kw: float) -> int:
    return _signed_register(value_kw)
