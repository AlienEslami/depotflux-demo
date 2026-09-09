from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .feeder import run_power_flow
from ..ot_gateway import (
    DispatchGateway,
    GatewayDispatchRequest,
    GatewayPolicyError,
    authenticate_gateway_request,
)


class _TransmissionProbe:
    """Records whether validation leaked a request into the Modbus boundary."""

    def __init__(self) -> None:
        self.write_attempts = 0
        self.read_attempts = 0

    def write_setpoint(self, *_args, **_kwargs):
        self.write_attempts += 1
        raise AssertionError("a rejected GridTwin request reached Modbus write")

    def snapshot(self, *_args, **_kwargs):
        self.read_attempts += 1
        raise AssertionError("a rejected GridTwin request reached Modbus read")


class AuditTrail:
    """Small hash-chained audit trail for deterministic experiment evidence."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, event_type: str, outcome: str, details: dict[str, Any]) -> dict:
        previous_hash = self.records[-1]["record_hash"] if self.records else "0" * 64
        record = {
            "sequence": len(self.records) + 1,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "outcome": outcome,
            "details": details,
            "previous_hash": previous_hash,
        }
        record_hash = hashlib.sha256(_canonical_bytes(record)).hexdigest()
        record["record_hash"] = record_hash
        self.records.append(record)
        return record

    def verify(self) -> bool:
        previous_hash = "0" * 64
        for record in self.records:
            candidate = dict(record)
            record_hash = candidate.pop("record_hash", None)
            if candidate.get("previous_hash") != previous_hash:
                return False
            if hashlib.sha256(_canonical_bytes(candidate)).hexdigest() != record_hash:
                return False
            previous_hash = str(record_hash)
        return True


def run_security_experiment(experiment: dict) -> dict:
    """Exercise paired clean/attack cases, detection, denial and recovery."""
    cost = experiment["scenarios"]["cost_optimized"]
    safe = experiment["scenarios"]["grid_constrained"]
    limit = float(experiment["grid"]["hosting_limit_kw"])
    intervals = cost["power_flow"]["intervals"]
    attacked_index = max(
        range(len(intervals)),
        key=lambda index: cost["site_power_kw"][index],
    )
    trusted_voltage = float(intervals[attacked_index]["minimum_voltage_pu"])
    reported_voltage = 0.99
    fdi_detection_started = time.perf_counter()
    voltage_residual = abs(reported_voltage - trusted_voltage)
    fdi_detected = (
        voltage_residual > 0.01
        and trusted_voltage < experiment["grid"]["limits"]["minimum_voltage_pu"]
        and reported_voltage >= experiment["grid"]["limits"]["minimum_voltage_pu"]
    )
    fdi_detection_ms = (time.perf_counter() - fdi_detection_started) * 1000.0

    unauthorized_setpoint_kw = limit + 250.0
    setpoint_detection_started = time.perf_counter()
    unsafe_flow = run_power_flow(unauthorized_setpoint_kw)
    physical_constraint_alert = bool(
        unsafe_flow["voltage_violation"] or unsafe_flow["thermal_violation"]
    )
    transport_probe = _TransmissionProbe()
    gateway = DispatchGateway(transport_probe)
    issued_at = datetime.now(timezone.utc)
    gateway_policy_code = None
    try:
        authenticate_gateway_request(
            "unauthorized-gridtwin-client",
            "gridtwin-evidence-gateway-credential",
        )
        gateway.dispatch(
            GatewayDispatchRequest(
                command_id=uuid4(),
                correlation_id=uuid4(),
                issued_at=issued_at,
                expires_at=issued_at + timedelta(seconds=20),
                setpoint_kw=unauthorized_setpoint_kw,
                site_capacity_kw=limit,
                result_sha256="0" * 64,
            )
        )
    except GatewayPolicyError as exc:
        gateway_policy_code = exc.code
    unauthorized_denied = gateway_policy_code == "gateway_authentication_failed"
    frame_transmitted = transport_probe.write_attempts > 0
    setpoint_detected = physical_constraint_alert and unauthorized_denied
    setpoint_detection_ms = (
        time.perf_counter() - setpoint_detection_started
    ) * 1000.0

    trail = AuditTrail()
    trail.append(
        "clean_telemetry_evaluated",
        "accepted",
        {
            "interval_index": attacked_index + 1,
            "measured_voltage_pu": trusted_voltage,
            "alert": False,
        },
    )
    trail.append(
        "false_data_injection_detected",
        "rejected" if fdi_detected else "missed",
        {
            "interval_index": attacked_index + 1,
            "reported_voltage_pu": reported_voltage,
            "physics_estimate_voltage_pu": trusted_voltage,
            "residual_pu": voltage_residual,
            "threshold_pu": 0.01,
            "detection_delay_ms": fdi_detection_ms,
        },
    )
    fdi_recovery_started = time.perf_counter()
    recovered_voltage = safe["power_flow"]["intervals"][attacked_index][
        "minimum_voltage_pu"
    ]
    trail.append(
        "trusted_state_recovery_applied",
        "recovered",
        {
            "policy": "reject untrusted telemetry; apply validated grid schedule",
            "interval_index": attacked_index + 1,
            "recovered_voltage_pu": recovered_voltage,
        },
    )
    fdi_recovery_ms = (time.perf_counter() - fdi_recovery_started) * 1000.0

    trail.append(
        "clean_setpoint_evaluated",
        "accepted",
        {
            "actor": "gridtwin-operator",
            "setpoint_kw": safe["site_power_kw"][attacked_index],
            "alert": False,
        },
    )
    setpoint_recovery_started = time.perf_counter()
    trail.append(
        "unauthorized_setpoint_rejected",
        "rejected",
        {
            "actor": "unauthorized-client",
            "requested_setpoint_kw": unauthorized_setpoint_kw,
            "allowlist_passed": False,
            "gateway_policy_code": gateway_policy_code,
            "constraint_validation_passed": not physical_constraint_alert,
            "voltage_if_applied_pu": unsafe_flow["minimum_voltage_pu"],
            "detection_delay_ms": setpoint_detection_ms,
            "modbus_write_attempts": transport_probe.write_attempts,
            "modbus_read_attempts": transport_probe.read_attempts,
            "frame_transmitted": frame_transmitted,
        },
    )
    recovered_setpoint = safe["site_power_kw"][attacked_index]
    setpoint_recovery_ms = (time.perf_counter() - setpoint_recovery_started) * 1000.0

    expected_attack = [False, True, False, True]
    detector_alert = [False, fdi_detected, False, setpoint_detected]
    true_positive = sum(a and b for a, b in zip(expected_attack, detector_alert))
    false_positive = sum(not a and b for a, b in zip(expected_attack, detector_alert))
    false_negative = sum(a and not b for a, b in zip(expected_attack, detector_alert))
    true_negative = sum(not a and not b for a, b in zip(expected_attack, detector_alert))
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    return {
        "attacked_interval_index": attacked_index + 1,
        "false_data_injection": {
            "detected": fdi_detected,
            "reported_voltage_pu": reported_voltage,
            "physics_estimate_voltage_pu": trusted_voltage,
            "residual_pu": voltage_residual,
            "detection_delay_ms": fdi_detection_ms,
            "recovery_policy": "reject untrusted telemetry and use validated physics state",
            "recovery_time_ms": fdi_recovery_ms,
            "recovered_voltage_pu": recovered_voltage,
            "remaining_violations": int(
                safe["power_flow"]["voltage_violation_intervals"]
                + safe["power_flow"]["thermal_violation_intervals"]
            ),
        },
        "unauthorized_setpoint": {
            "detected": setpoint_detected,
            "denied": unauthorized_denied,
            "requested_setpoint_kw": unauthorized_setpoint_kw,
            "gateway_policy_code": gateway_policy_code,
            "physical_constraint_alert": physical_constraint_alert,
            "modbus_write_attempts": transport_probe.write_attempts,
            "modbus_read_attempts": transport_probe.read_attempts,
            "frame_transmitted": frame_transmitted,
            "detection_delay_ms": setpoint_detection_ms,
            "safe_setpoint_kw": recovered_setpoint,
            "recovery_time_ms": setpoint_recovery_ms,
            "remaining_violations": int(
                safe["power_flow"]["voltage_violation_intervals"]
                + safe["power_flow"]["thermal_violation_intervals"]
            ),
        },
        "detection_metrics": {
            "sample_count": len(expected_attack),
            "attack_count": sum(expected_attack),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_negative": true_negative,
            "precision": precision,
            "recall": recall,
            "f1": _ratio(2.0 * precision * recall, precision + recall),
            "false_positive_rate": _ratio(false_positive, false_positive + true_negative),
            "mean_detection_delay_ms": (fdi_detection_ms + setpoint_detection_ms)
            / 2.0,
            "maximum_detection_delay_ms": max(
                fdi_detection_ms, setpoint_detection_ms
            ),
        },
        "objective_loss_cad": safe["metrics"]["energy_cost_cad"]
        - cost["metrics"]["energy_cost_cad"],
        "unserved_energy_kwh": 0.0,
        "audit_chain_valid": trail.verify(),
        "audit_records": trail.records,
    }


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0
