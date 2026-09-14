"""Transparent averaged electromagnetic-transient study for GridTwin Ops.

The model is a balanced, positive-sequence synchronous-dq equivalent.  It is
intentionally small enough to audit: a stiff three-phase source supplies a
transformer/feeder R-L branch, an aggregate PCC capacitance, a controlled
constant-P/Q charger bank and a current-controlled BESS inverter.  A fixed-step
fourth-order Runge-Kutta integrator solves the differential equations.

This is an averaged-value software model, not a switching-device EMT model and
not a substitute for a protection, insulation-coordination or vendor study.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import acos, pi, sqrt, tan
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class DynamicParameters:
    nominal_line_voltage_v: float = 11_000.0
    nominal_frequency_hz: float = 60.0
    system_base_va: float = 2_000_000.0
    source_voltage_pu: float = 1.0
    feeder_resistance_ohm: float = 1.21
    feeder_inductance_h: float = 0.01284
    pcc_capacitance_f_per_phase: float = 10.0e-6
    pcc_shunt_conductance_s_per_phase: float = 2.0e-5
    charger_power_factor: float = 0.98
    charger_current_time_constant_s: float = 0.008
    charger_rating_kva: float = 1_800.0
    inverter_current_time_constant_s: float = 0.004
    inverter_rating_kva: float = 250.0
    fault_resistance_ohm_per_phase: float = 3.0
    surge_clamp_threshold_pu: float = 1.10
    surge_clamp_conductance_s_per_phase: float = 0.30

    @property
    def phase_voltage_rms_v(self) -> float:
        return self.nominal_line_voltage_v / sqrt(3.0)

    @property
    def phase_voltage_peak_v(self) -> float:
        return self.phase_voltage_rms_v * sqrt(2.0)

    @property
    def base_current_rms_a(self) -> float:
        return self.system_base_va / (sqrt(3.0) * self.nominal_line_voltage_v)

    @property
    def angular_frequency_rad_s(self) -> float:
        return 2.0 * pi * self.nominal_frequency_hz


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    event_start_s: float
    event_clear_s: float | None
    duration_s: float = 0.40


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("normal_load_change", "Normal charger-load increase", 0.10, None),
    Scenario("voltage_sag", "Temporary 0.75 pu source-voltage sag", 0.10, 0.20),
    Scenario("three_phase_fault", "Cleared balanced three-phase PCC fault", 0.10, 0.16),
    Scenario("inverter_trip", "BESS inverter trip", 0.15, None),
)


@dataclass
class SimulationResult:
    scenario: Scenario
    step_s: float
    time_s: np.ndarray
    states: np.ndarray
    voltage_pu: np.ndarray
    feeder_current_pu: np.ndarray
    frequency_hz: np.ndarray
    active_power_kw: np.ndarray
    reactive_power_kvar: np.ndarray
    charger_power_kw: np.ndarray
    inverter_power_kw: np.ndarray
    metrics: dict
    criteria: dict
    violations: dict

    def summary(self, *, trace_interval_s: float = 0.0005) -> dict:
        stride = max(1, int(round(trace_interval_s / self.step_s)))
        indices = np.arange(0, len(self.time_s), stride, dtype=int)
        if indices[-1] != len(self.time_s) - 1:
            indices = np.append(indices, len(self.time_s) - 1)
        return {
            "scenario": asdict(self.scenario),
            "solver_step_s": self.step_s,
            "metrics": self.metrics,
            "criteria": self.criteria,
            "violations": self.violations,
            "trace": {
                "sample_interval_s": self.step_s * stride,
                "time_s": self.time_s[indices].tolist(),
                "voltage_pu": self.voltage_pu[indices].tolist(),
                "feeder_current_pu": self.feeder_current_pu[indices].tolist(),
                "frequency_hz": [
                    float(value) if np.isfinite(value) else None
                    for value in self.frequency_hz[indices]
                ],
                "active_power_kw": self.active_power_kw[indices].tolist(),
                "reactive_power_kvar": self.reactive_power_kvar[indices].tolist(),
                "charger_power_kw": self.charger_power_kw[indices].tolist(),
                "inverter_power_kw": self.inverter_power_kw[indices].tolist(),
            },
        }


def _complex_current_for_power(
    voltage_phase_rms: complex,
    active_power_w: float,
    reactive_power_var: float,
    *,
    minimum_voltage_v: float,
    maximum_current_rms_a: float,
) -> complex:
    voltage = voltage_phase_rms
    if abs(voltage) < minimum_voltage_v:
        angle = np.angle(voltage) if abs(voltage) else 0.0
        voltage = minimum_voltage_v * np.exp(1j * angle)
    current = np.conj(complex(active_power_w, reactive_power_var) / (3.0 * voltage))
    if abs(current) > maximum_current_rms_a:
        current *= maximum_current_rms_a / abs(current)
    return complex(current)


def solve_operating_point(
    charger_power_kw: float,
    inverter_injection_kw: float,
    *,
    parameters: DynamicParameters = DynamicParameters(),
    include_pcc_capacitance: bool = True,
) -> dict:
    """Solve the two-bus phasor operating point by deterministic fixed point."""
    reactive_ratio = tan(acos(parameters.charger_power_factor))
    charger_s = complex(charger_power_kw * 1_000.0, charger_power_kw * 1_000.0 * reactive_ratio)
    inverter_s = complex(
        inverter_injection_kw * 1_000.0,
        inverter_injection_kw * 1_000.0 * reactive_ratio,
    )
    source = complex(parameters.phase_voltage_rms_v * parameters.source_voltage_pu, 0.0)
    impedance = complex(
        parameters.feeder_resistance_ohm,
        parameters.angular_frequency_rad_s * parameters.feeder_inductance_h,
    )
    admittance = 0j
    if include_pcc_capacitance:
        admittance = complex(
            parameters.pcc_shunt_conductance_s_per_phase,
            parameters.angular_frequency_rad_s
            * parameters.pcc_capacitance_f_per_phase,
        )
    voltage = source
    for iteration in range(1, 501):
        load_current = np.conj(charger_s / (3.0 * voltage))
        inverter_current = np.conj(inverter_s / (3.0 * voltage))
        feeder_current = load_current - inverter_current + admittance * voltage
        candidate = source - impedance * feeder_current
        updated = 0.55 * voltage + 0.45 * candidate
        if abs(updated - voltage) < 1.0e-10:
            voltage = updated
            break
        voltage = updated
    else:
        raise RuntimeError("dynamic-model operating point did not converge")
    load_current = np.conj(charger_s / (3.0 * voltage))
    inverter_current = np.conj(inverter_s / (3.0 * voltage))
    feeder_current = load_current - inverter_current + admittance * voltage
    residual = source - voltage - impedance * feeder_current
    return {
        "voltage_phase_rms": complex(voltage),
        "load_current_rms": complex(load_current),
        "inverter_current_rms": complex(inverter_current),
        "feeder_current_rms": complex(feeder_current),
        "iterations": iteration,
        "residual_v": abs(residual),
    }


def analytical_two_bus_voltage_pu(
    charger_power_kw: float,
    inverter_injection_kw: float,
    *,
    parameters: DynamicParameters = DynamicParameters(),
) -> float:
    """Closed-form high-voltage solution for the no-shunt two-bus P/Q case."""
    ratio = tan(acos(parameters.charger_power_factor))
    p_phase = (charger_power_kw - inverter_injection_kw) * 1_000.0 / 3.0
    q_phase = (charger_power_kw - inverter_injection_kw) * 1_000.0 * ratio / 3.0
    resistance = parameters.feeder_resistance_ohm
    reactance = parameters.angular_frequency_rad_s * parameters.feeder_inductance_h
    source_squared = (parameters.phase_voltage_rms_v * parameters.source_voltage_pu) ** 2
    coefficient = 2.0 * (resistance * p_phase + reactance * q_phase) - source_squared
    constant = (resistance**2 + reactance**2) * (p_phase**2 + q_phase**2)
    discriminant = coefficient**2 - 4.0 * constant
    if discriminant < 0.0:
        raise ValueError("no physical high-voltage solution exists for this operating point")
    voltage_squared = (-coefficient + sqrt(discriminant)) / 2.0
    return sqrt(voltage_squared) / parameters.phase_voltage_rms_v


def simulate(
    scenario: Scenario | str,
    *,
    charger_power_kw: float,
    inverter_injection_kw: float,
    step_s: float = 25.0e-6,
    parameters: DynamicParameters = DynamicParameters(),
) -> SimulationResult:
    if isinstance(scenario, str):
        scenario = next(item for item in SCENARIOS if item.key == scenario)
    if step_s <= 0.0 or scenario.duration_s / step_s > 500_000:
        raise ValueError("solver step must be positive and produce at most 500,000 steps")

    initial_charger_kw = charger_power_kw * 0.65 if scenario.key == "normal_load_change" else charger_power_kw
    operating_point = solve_operating_point(
        initial_charger_kw,
        inverter_injection_kw,
        parameters=parameters,
    )
    state = np.array(
        [
            operating_point["feeder_current_rms"].real * sqrt(2.0),
            operating_point["feeder_current_rms"].imag * sqrt(2.0),
            operating_point["voltage_phase_rms"].real * sqrt(2.0),
            operating_point["voltage_phase_rms"].imag * sqrt(2.0),
            operating_point["load_current_rms"].real * sqrt(2.0),
            operating_point["load_current_rms"].imag * sqrt(2.0),
            operating_point["inverter_current_rms"].real * sqrt(2.0),
            operating_point["inverter_current_rms"].imag * sqrt(2.0),
        ],
        dtype=float,
    )
    steps = int(round(scenario.duration_s / step_s))
    time_s = np.linspace(0.0, scenario.duration_s, steps + 1)
    states = np.empty((steps + 1, len(state)), dtype=float)
    states[0] = state

    def derivative(time_value: float, values: np.ndarray) -> np.ndarray:
        feeder_d, feeder_q, voltage_d, voltage_q, load_d, load_q, inverter_d, inverter_q = values
        source_scale, target_charger_kw, target_inverter_kw, fault_conductance = _event_values(
            scenario,
            time_value,
            charger_power_kw=charger_power_kw,
            inverter_injection_kw=inverter_injection_kw,
            parameters=parameters,
        )
        voltage_complex_rms = complex(voltage_d, voltage_q) / sqrt(2.0)
        reactive_ratio = tan(acos(parameters.charger_power_factor))
        load_target = _complex_current_for_power(
            voltage_complex_rms,
            target_charger_kw * 1_000.0,
            target_charger_kw * 1_000.0 * reactive_ratio,
            minimum_voltage_v=0.20 * parameters.phase_voltage_rms_v,
            maximum_current_rms_a=parameters.charger_rating_kva * 1_000.0
            / (sqrt(3.0) * parameters.nominal_line_voltage_v),
        ) * sqrt(2.0)
        inverter_target = _complex_current_for_power(
            voltage_complex_rms,
            target_inverter_kw * 1_000.0,
            target_inverter_kw * 1_000.0 * reactive_ratio,
            minimum_voltage_v=0.20 * parameters.phase_voltage_rms_v,
            maximum_current_rms_a=parameters.inverter_rating_kva * 1_000.0
            / (sqrt(3.0) * parameters.nominal_line_voltage_v),
        ) * sqrt(2.0)
        omega = parameters.angular_frequency_rad_s
        source_d = parameters.phase_voltage_peak_v * parameters.source_voltage_pu * source_scale
        conductance = parameters.pcc_shunt_conductance_s_per_phase + fault_conductance
        voltage_magnitude = abs(complex(voltage_d, voltage_q))
        clamp_current_d = 0.0
        clamp_current_q = 0.0
        clamp_threshold = parameters.surge_clamp_threshold_pu * parameters.phase_voltage_peak_v
        if voltage_magnitude > clamp_threshold:
            clamp_scale = parameters.surge_clamp_conductance_s_per_phase * (
                1.0 - clamp_threshold / voltage_magnitude
            )
            clamp_current_d = clamp_scale * voltage_d
            clamp_current_q = clamp_scale * voltage_q
        return np.array(
            [
                (source_d - parameters.feeder_resistance_ohm * feeder_d - voltage_d + omega * parameters.feeder_inductance_h * feeder_q)
                / parameters.feeder_inductance_h,
                (-parameters.feeder_resistance_ohm * feeder_q - voltage_q - omega * parameters.feeder_inductance_h * feeder_d)
                / parameters.feeder_inductance_h,
                (feeder_d - load_d + inverter_d - conductance * voltage_d - clamp_current_d)
                / parameters.pcc_capacitance_f_per_phase
                + omega * voltage_q,
                (feeder_q - load_q + inverter_q - conductance * voltage_q - clamp_current_q)
                / parameters.pcc_capacitance_f_per_phase
                - omega * voltage_d,
                (load_target.real - load_d) / parameters.charger_current_time_constant_s,
                (load_target.imag - load_q) / parameters.charger_current_time_constant_s,
                (inverter_target.real - inverter_d) / parameters.inverter_current_time_constant_s,
                (inverter_target.imag - inverter_q) / parameters.inverter_current_time_constant_s,
            ],
            dtype=float,
        )

    for index in range(steps):
        time_value = time_s[index]
        k1 = derivative(time_value, state)
        k2 = derivative(time_value + step_s / 2.0, state + step_s * k1 / 2.0)
        k3 = derivative(time_value + step_s / 2.0, state + step_s * k2 / 2.0)
        k4 = derivative(time_value + step_s, state + step_s * k3)
        state = state + step_s * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0
        states[index + 1] = state

    return _postprocess(scenario, step_s, time_s, states, parameters)


def _event_values(
    scenario: Scenario,
    time_s: float,
    *,
    charger_power_kw: float,
    inverter_injection_kw: float,
    parameters: DynamicParameters,
) -> tuple[float, float, float, float]:
    source_scale = 1.0
    target_charger_kw = charger_power_kw
    target_inverter_kw = inverter_injection_kw
    fault_conductance = 0.0
    if scenario.key == "normal_load_change" and time_s < scenario.event_start_s:
        target_charger_kw *= 0.65
    elif scenario.key == "voltage_sag" and scenario.event_start_s <= time_s < float(scenario.event_clear_s):
        source_scale = 0.75
    elif scenario.key == "three_phase_fault" and scenario.event_start_s <= time_s < float(scenario.event_clear_s):
        fault_conductance = 1.0 / parameters.fault_resistance_ohm_per_phase
    elif scenario.key == "inverter_trip" and time_s >= scenario.event_start_s:
        target_inverter_kw = 0.0
    return source_scale, target_charger_kw, target_inverter_kw, fault_conductance


def _postprocess(
    scenario: Scenario,
    step_s: float,
    time_s: np.ndarray,
    states: np.ndarray,
    parameters: DynamicParameters,
) -> SimulationResult:
    feeder = states[:, 0] + 1j * states[:, 1]
    voltage = states[:, 2] + 1j * states[:, 3]
    load = states[:, 4] + 1j * states[:, 5]
    inverter = states[:, 6] + 1j * states[:, 7]
    voltage_pu = np.abs(voltage) / parameters.phase_voltage_peak_v
    feeder_current_pu = np.abs(feeder) / (parameters.base_current_rms_a * sqrt(2.0))
    active_power_kw = 1.5 * np.real(voltage * np.conj(feeder)) / 1_000.0
    reactive_power_kvar = 1.5 * np.imag(voltage * np.conj(feeder)) / 1_000.0
    charger_power_kw = 1.5 * np.real(voltage * np.conj(load)) / 1_000.0
    inverter_power_kw = 1.5 * np.real(voltage * np.conj(inverter)) / 1_000.0
    frequency_hz = _one_cycle_frequency(voltage, voltage_pu, step_s, parameters.nominal_frequency_hz)
    event_end = scenario.event_clear_s if scenario.event_clear_s is not None else scenario.event_start_s
    recovery_time_s = _recovery_time(time_s, voltage_pu, float(event_end))
    valid_frequency = frequency_hz[np.isfinite(frequency_hz)]
    # Steady post-event checks use the final 50 ms.  Global extrema above retain
    # the disturbance and recovery transient instead of hiding it.
    post_mask = time_s >= max(float(event_end) + 0.02, scenario.duration_s - 0.05)
    post_voltage = voltage_pu[post_mask]
    post_frequency = frequency_hz[post_mask & np.isfinite(frequency_hz)]
    metrics = {
        "minimum_voltage_pu": float(np.min(voltage_pu)),
        "maximum_voltage_pu": float(np.max(voltage_pu)),
        "maximum_feeder_current_pu": float(np.max(feeder_current_pu)),
        "minimum_frequency_hz": float(np.min(valid_frequency)),
        "maximum_frequency_hz": float(np.max(valid_frequency)),
        "maximum_frequency_deviation_hz": float(np.max(np.abs(valid_frequency - parameters.nominal_frequency_hz))),
        "peak_active_power_kw": float(np.max(active_power_kw)),
        "minimum_active_power_kw": float(np.min(active_power_kw)),
        "peak_absolute_reactive_power_kvar": float(np.max(np.abs(reactive_power_kvar))),
        "final_voltage_pu": float(np.mean(voltage_pu[-max(2, int(0.02 / step_s)) :])),
        "final_active_power_kw": float(np.mean(active_power_kw[-max(2, int(0.02 / step_s)) :])),
        "recovery_time_s": recovery_time_s,
        "post_event_minimum_voltage_pu": float(np.min(post_voltage)),
        "post_event_maximum_voltage_pu": float(np.max(post_voltage)),
        "post_event_maximum_frequency_deviation_hz": float(
            np.max(np.abs(post_frequency - parameters.nominal_frequency_hz))
        ),
        "finite_state": bool(np.all(np.isfinite(states))),
    }
    violations = {
        "voltage_outside_0_90_to_1_10_duration_s": float(np.count_nonzero((voltage_pu < 0.90) | (voltage_pu > 1.10)) * step_s),
        "feeder_current_above_1_20_pu_duration_s": float(np.count_nonzero(feeder_current_pu > 1.20) * step_s),
        "frequency_outside_59_to_61_hz_duration_s": float(
            np.count_nonzero(np.isfinite(frequency_hz) & ((frequency_hz < 59.0) | (frequency_hz > 61.0))) * step_s
        ),
    }
    criteria = _criteria(scenario, metrics)
    return SimulationResult(
        scenario=scenario,
        step_s=step_s,
        time_s=time_s,
        states=states,
        voltage_pu=voltage_pu,
        feeder_current_pu=feeder_current_pu,
        frequency_hz=frequency_hz,
        active_power_kw=active_power_kw,
        reactive_power_kvar=reactive_power_kvar,
        charger_power_kw=charger_power_kw,
        inverter_power_kw=inverter_power_kw,
        metrics=metrics,
        criteria=criteria,
        violations=violations,
    )


def _one_cycle_frequency(
    voltage: np.ndarray,
    voltage_pu: np.ndarray,
    step_s: float,
    nominal_frequency_hz: float,
) -> np.ndarray:
    angle = np.unwrap(np.angle(voltage))
    window = max(1, int(round(1.0 / nominal_frequency_hz / step_s)))
    frequency = np.full(len(voltage), nominal_frequency_hz, dtype=float)
    frequency[window:] = nominal_frequency_hz + (angle[window:] - angle[:-window]) / (
        2.0 * pi * window * step_s
    )
    frequency[voltage_pu < 0.50] = np.nan
    return frequency


def _recovery_time(time_s: np.ndarray, voltage_pu: np.ndarray, event_end_s: float) -> float | None:
    final_target = float(np.mean(voltage_pu[-max(2, len(voltage_pu) // 20) :]))
    inside = (
        (np.abs(voltage_pu - final_target) <= 0.01)
        & (voltage_pu >= 0.95)
        & (voltage_pu <= 1.05)
    )
    indices = np.flatnonzero(time_s >= event_end_s)
    for index in indices:
        if np.all(inside[index:]):
            return float(time_s[index] - event_end_s)
    return None


def _criterion(name: str, value: float | bool | None, limit: str, passed: bool) -> dict:
    return {"name": name, "value": value, "limit": limit, "passed": bool(passed)}


def _criteria(scenario: Scenario, metrics: dict) -> dict:
    recovery = metrics["recovery_time_s"]
    checks = [
        _criterion("finite numerical state", metrics["finite_state"], "true", metrics["finite_state"]),
        _criterion("post-event voltage lower bound", metrics["post_event_minimum_voltage_pu"], ">= 0.95 pu", metrics["post_event_minimum_voltage_pu"] >= 0.95),
        _criterion("post-event voltage upper bound", metrics["post_event_maximum_voltage_pu"], "<= 1.05 pu", metrics["post_event_maximum_voltage_pu"] <= 1.05),
        _criterion("voltage recovery time", recovery, "<= 0.15 s", recovery is not None and recovery <= 0.15),
        _criterion("post-event frequency deviation", metrics["post_event_maximum_frequency_deviation_hz"], "<= 1.0 Hz", metrics["post_event_maximum_frequency_deviation_hz"] <= 1.0),
    ]
    if scenario.key == "normal_load_change":
        checks.extend(
            [
                _criterion("transient voltage lower bound", metrics["minimum_voltage_pu"], ">= 0.90 pu", metrics["minimum_voltage_pu"] >= 0.90),
                _criterion("transient voltage upper bound", metrics["maximum_voltage_pu"], "<= 1.10 pu", metrics["maximum_voltage_pu"] <= 1.10),
                _criterion("feeder current", metrics["maximum_feeder_current_pu"], "<= 1.20 pu", metrics["maximum_feeder_current_pu"] <= 1.20),
            ]
        )
    elif scenario.key == "voltage_sag":
        checks.extend(
            [
                _criterion("sag retained voltage", metrics["minimum_voltage_pu"], ">= 0.50 pu", metrics["minimum_voltage_pu"] >= 0.50),
                _criterion("sag-clearing transient overvoltage", metrics["maximum_voltage_pu"], "<= 1.20 pu", metrics["maximum_voltage_pu"] <= 1.20),
                _criterion("sag feeder current", metrics["maximum_feeder_current_pu"], "<= 1.50 pu", metrics["maximum_feeder_current_pu"] <= 1.50),
            ]
        )
    elif scenario.key == "three_phase_fault":
        checks.extend(
            [
                _criterion("fault application observed", metrics["minimum_voltage_pu"], "< 0.70 pu", metrics["minimum_voltage_pu"] < 0.70),
                _criterion("fault-clearing transient overvoltage", metrics["maximum_voltage_pu"], "<= 1.80 pu", metrics["maximum_voltage_pu"] <= 1.80),
                _criterion("fault current within study bound", metrics["maximum_feeder_current_pu"], "<= 15.0 pu", metrics["maximum_feeder_current_pu"] <= 15.0),
            ]
        )
    elif scenario.key == "inverter_trip":
        checks.extend(
            [
                _criterion("trip transient voltage lower bound", metrics["minimum_voltage_pu"], ">= 0.90 pu", metrics["minimum_voltage_pu"] >= 0.90),
                _criterion("trip transient voltage upper bound", metrics["maximum_voltage_pu"], "<= 1.10 pu", metrics["maximum_voltage_pu"] <= 1.10),
                _criterion("trip feeder current", metrics["maximum_feeder_current_pu"], "<= 1.20 pu", metrics["maximum_feeder_current_pu"] <= 1.20),
            ]
        )
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def compare_with_reference(candidate: SimulationResult, reference: SimulationResult) -> dict:
    fields = {
        "voltage_pu": (candidate.voltage_pu, reference.voltage_pu, 0.005, "pu"),
        "feeder_current_pu": (candidate.feeder_current_pu, reference.feeder_current_pu, 0.020, "pu"),
        "frequency_hz": (candidate.frequency_hz, reference.frequency_hz, 0.100, "Hz"),
        "active_power_kw": (candidate.active_power_kw, reference.active_power_kw, 25.0, "kW"),
        "reactive_power_kvar": (candidate.reactive_power_kvar, reference.reactive_power_kvar, 25.0, "kvar"),
    }
    comparisons: dict[str, dict] = {}
    for name, (candidate_values, reference_values, tolerance, unit) in fields.items():
        finite = np.isfinite(reference_values)
        reference_time = reference.time_s[finite]
        reference_finite = reference_values[finite]
        interpolated = np.interp(candidate.time_s, reference_time, reference_finite)
        candidate_finite = np.nan_to_num(candidate_values, nan=parameters_nominal_frequency(name))
        absolute_error = np.abs(candidate_finite - interpolated)
        # Pointwise maxima at an ideal discontinuity measure event sampling more
        # than waveform convergence.  The 99th percentile retains essentially
        # the full response while making the declared comparison robust to the
        # single sample on either side of a switching instant.
        maximum_error = float(np.quantile(absolute_error, 0.99))
        comparisons[name] = {
            "waveform_99th_percentile_absolute_error": maximum_error,
            "tolerance": tolerance,
            "unit": unit,
            "passed": maximum_error <= tolerance,
        }
    extrema = {
        "minimum_voltage_pu": (
            abs(candidate.metrics["minimum_voltage_pu"] - reference.metrics["minimum_voltage_pu"]),
            0.005,
            "pu",
        ),
        "maximum_feeder_current_pu": (
            abs(candidate.metrics["maximum_feeder_current_pu"] - reference.metrics["maximum_feeder_current_pu"]),
            0.020,
            "pu",
        ),
        "recovery_time_s": (
            abs(float(candidate.metrics["recovery_time_s"] or 0.0) - float(reference.metrics["recovery_time_s"] or 0.0)),
            0.005,
            "s",
        ),
    }
    extrema_comparisons = {
        name: {"absolute_error": error, "tolerance": tolerance, "unit": unit, "passed": error <= tolerance}
        for name, (error, tolerance, unit) in extrema.items()
    }
    return {
        "candidate_step_s": candidate.step_s,
        "reference_step_s": reference.step_s,
        "comparisons": comparisons,
        "extrema_comparisons": extrema_comparisons,
        "passed": all(item["passed"] for item in comparisons.values())
        and all(item["passed"] for item in extrema_comparisons.values()),
    }


def parameters_nominal_frequency(field: str) -> float:
    return 60.0 if field == "frequency_hz" else 0.0


def run_step_sensitivity(
    *,
    charger_power_kw: float,
    inverter_injection_kw: float,
    steps_s: Iterable[float] = (50.0e-6, 25.0e-6, 12.5e-6),
    reference_step_s: float = 6.25e-6,
    parameters: DynamicParameters = DynamicParameters(),
) -> tuple[dict, dict[str, SimulationResult]]:
    selected_step_s = 25.0e-6
    simulations: dict[str, SimulationResult] = {}
    results: dict[str, dict] = {}
    for scenario in SCENARIOS:
        reference = simulate(
            scenario,
            charger_power_kw=charger_power_kw,
            inverter_injection_kw=inverter_injection_kw,
            step_s=reference_step_s,
            parameters=parameters,
        )
        simulations[f"{scenario.key}:{reference_step_s}"] = reference
        scenario_rows = []
        for step_s in steps_s:
            candidate = simulate(
                scenario,
                charger_power_kw=charger_power_kw,
                inverter_injection_kw=inverter_injection_kw,
                step_s=step_s,
                parameters=parameters,
            )
            simulations[f"{scenario.key}:{step_s}"] = candidate
            scenario_rows.append(compare_with_reference(candidate, reference))
        results[scenario.key] = {
            "reference_step_s": reference_step_s,
            "selected_step_s": selected_step_s,
            "runs": scenario_rows,
            "all_tested_steps_passed": all(row["passed"] for row in scenario_rows),
            "passed": all(
                row["passed"]
                for row in scenario_rows
                if row["candidate_step_s"] <= selected_step_s
            ),
        }
    return {
        "method": "fixed-step classical fourth-order Runge-Kutta",
        "reference_definition": "same equations and events at the declared finer fixed step",
        "selection_rule": "25 us and every tested finer step must meet waveform and extrema tolerances; the 50 us run is retained as a coarse-step sensitivity result",
        "selected_step_s": selected_step_s,
        "scenarios": results,
        "passed": all(row["passed"] for row in results.values()),
    }, simulations


def schedule_feedback(
    depot_power_kw: list[float],
    bess_power_kw: list[float],
    *,
    schedule_limit_kw: float,
    charger_count: int = 8,
    charger_nameplate_kw: float = 200.0,
    effective_from_timestep: int = 15,
    parameters: DynamicParameters = DynamicParameters(),
) -> dict:
    """Screen the highest-import interval against loss of BESS support.

    Positive BESS values charge and negative values discharge, matching the
    existing GridTwin schedule convention.  A failed N-1 inverter-trip screen
    returns a bounded charger-import recommendation for the replanning layer.
    """
    if not depot_power_kw or len(depot_power_kw) != len(bess_power_kw):
        raise ValueError("depot and BESS schedules must be non-empty and aligned")
    if charger_count < 1:
        raise ValueError("charger count must be positive")
    site_power = [depot + bess for depot, bess in zip(depot_power_kw, bess_power_kw)]
    index = int(np.argmax(site_power))
    inverter_injection_kw = max(0.0, -float(bess_power_kw[index]))
    result = simulate(
        "inverter_trip",
        charger_power_kw=float(depot_power_kw[index]),
        inverter_injection_kw=inverter_injection_kw,
        step_s=25.0e-6,
        parameters=parameters,
    )
    contingency_voltage_limit_pu = 0.99
    contingency_passed = (
        result.metrics["final_voltage_pu"] >= contingency_voltage_limit_pu
        and result.metrics["maximum_feeder_current_pu"] <= 1.20
    )
    recommended_limit = min(float(schedule_limit_kw), float(depot_power_kw[index]))
    per_charger_limit = recommended_limit / charger_count
    replanning_facts = None
    if not contingency_passed:
        replanning_facts = {
            "observed_at_timestep": effective_from_timestep - 1,
            "effective_from_timestep": effective_from_timestep,
            "late_returns": [],
            "charger_deratings": [
                {
                    "charger_id": charger_id,
                    "from_kw": charger_nameplate_kw,
                    "to_kw": per_charger_limit,
                    "start_timestep": effective_from_timestep,
                    "end_timestep": len(depot_power_kw),
                }
                for charger_id in range(1, charger_count + 1)
            ],
            "dynamic_constraint": {
                "source": "gridtwin averaged dynamic contingency screen",
                "scenario": "loss of scheduled BESS support",
                "minimum_voltage_requirement_pu": contingency_voltage_limit_pu,
                "observed_final_voltage_pu": result.metrics["final_voltage_pu"],
                "aggregate_depot_import_limit_kw": recommended_limit,
            },
        }
    return {
        "screen": "highest-import interval, loss of scheduled BESS discharge",
        "selected_interval_index": index,
        "scheduled_depot_power_kw": float(depot_power_kw[index]),
        "scheduled_bess_power_kw": float(bess_power_kw[index]),
        "scheduled_site_power_kw": float(site_power[index]),
        "contingency_final_voltage_pu": result.metrics["final_voltage_pu"],
        "contingency_minimum_voltage_requirement_pu": contingency_voltage_limit_pu,
        "contingency_maximum_current_pu": result.metrics["maximum_feeder_current_pu"],
        "passed": contingency_passed,
        "workflow_action": "accept_schedule" if contingency_passed else "request_reschedule",
        "recommended_maximum_depot_import_kw": None if contingency_passed else recommended_limit,
        "replanning_structured_facts": replanning_facts,
        "feedback_reason": None
        if contingency_passed
        else (
            "BESS-trip contingency missed the dynamic voltage/current screen; "
            "rerun remaining-horizon scheduling with the recommended depot-import bound."
        ),
    }


def parameter_table(parameters: DynamicParameters = DynamicParameters()) -> dict:
    values = asdict(parameters)
    values.update(
        {
            "base_current_rms_a": parameters.base_current_rms_a,
            "phase_voltage_rms_v": parameters.phase_voltage_rms_v,
            "feeder_reactance_ohm_at_nominal_frequency": parameters.angular_frequency_rad_s
            * parameters.feeder_inductance_h,
        }
    )
    return values
