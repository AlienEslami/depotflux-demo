from __future__ import annotations

import math
import struct
from hmac import compare_digest


MODBUS_WRITE_SINGLE_REGISTER = 0x06
SITE_POWER_REGISTER = 100
SITE_POWER_SCALE_KW = 0.1


class ControlAuthenticationError(PermissionError):
    pass


class ControlPolicyError(RuntimeError):
    def __init__(self, message: str, *, failed_check: str = "policy_gate"):
        super().__init__(message)
        self.failed_check = failed_check


def authenticate_control_key(provided: str | None, configured: str | None) -> None:
    """Fail closed when the simulation credential is missing or incorrect."""
    if not configured:
        raise ControlAuthenticationError("control simulation is not configured")
    if not provided or not compare_digest(provided, configured):
        raise ControlAuthenticationError("invalid control simulation credential")


def validate_site_setpoint(setpoint_kw: float, *, site_capacity_kw: float) -> float:
    value = float(setpoint_kw)
    capacity = float(site_capacity_kw)
    if not math.isfinite(value):
        raise ControlPolicyError(
            "site setpoint must be finite",
            failed_check="finite_site_setpoint",
        )
    if not math.isfinite(capacity) or capacity <= 0:
        raise ControlPolicyError(
            "depot site capacity is invalid",
            failed_check="site_capacity_available",
        )
    if abs(value) > capacity + 1e-7:
        raise ControlPolicyError(
            f"site setpoint {value:.3f} kW exceeds the {capacity:.3f} kW envelope",
            failed_check="site_capacity_envelope",
        )
    return value


def encode_site_power_write(
    setpoint_kw: float,
    *,
    transaction_id: int,
    unit_id: int = 1,
    register_address: int = SITE_POWER_REGISTER,
    scale_kw: float = SITE_POWER_SCALE_KW,
) -> bytes:
    """Encode, but never transmit, a Modbus/TCP write-single-register request."""
    if not 0 <= transaction_id <= 65535:
        raise ControlPolicyError(
            "Modbus transaction ID is outside uint16 range",
            failed_check="modbus_transaction_id",
        )
    if not 1 <= unit_id <= 247:
        raise ControlPolicyError(
            "Modbus unit ID is outside the device range",
            failed_check="modbus_unit_id",
        )
    if not 0 <= register_address <= 65535:
        raise ControlPolicyError(
            "Modbus register address is outside uint16 range",
            failed_check="modbus_register_address",
        )
    if not math.isfinite(scale_kw) or scale_kw <= 0:
        raise ControlPolicyError(
            "Modbus register scale must be positive",
            failed_check="modbus_register_scale",
        )
    scaled = int(round(float(setpoint_kw) / scale_kw))
    if not -32768 <= scaled <= 32767:
        raise ControlPolicyError(
            "site setpoint cannot be represented in one signed register",
            failed_check="signed_register_range",
        )
    register_value = scaled & 0xFFFF
    return struct.pack(
        ">HHHBBHH",
        transaction_id,
        0,
        6,
        unit_id,
        MODBUS_WRITE_SINGLE_REGISTER,
        register_address,
        register_value,
    )


def decode_site_power_write(frame: bytes, *, scale_kw: float = SITE_POWER_SCALE_KW) -> dict:
    if len(frame) != 12:
        raise ValueError("write-single-register frame must contain 12 bytes")
    transaction_id, protocol_id, length, unit_id, function, address, raw = (
        struct.unpack(">HHHBBHH", frame)
    )
    if protocol_id != 0 or length != 6 or function != MODBUS_WRITE_SINGLE_REGISTER:
        raise ValueError("frame is not a Modbus/TCP write-single-register request")
    signed = raw - 65536 if raw >= 32768 else raw
    return {
        "transaction_id": transaction_id,
        "unit_id": unit_id,
        "register_address": address,
        "setpoint_kw": signed * scale_kw,
    }
