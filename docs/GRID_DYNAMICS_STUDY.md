# GridTwin averaged grid-dynamics study

Status: implemented synthetic portfolio study. The authoritative generated
artifacts are under `evidence/grid-dynamics/`.

## Scope and honest classification

The extension closes a specific gap between the existing 30-minute pandapower
snapshots and sub-second electrical behavior. It is a balanced,
positive-sequence synchronous-dq **averaged electromagnetic-transient model**
implemented in Python/NumPy and solved by a project-owned fixed-step classical
RK4 integrator. It resolves feeder and aggregate converter-current transients;
it does not resolve semiconductor switching, harmonics or phase unbalance.

No MATLAB/Simulink, Simscape Electrical, Specialized Power Systems, PSCAD,
EMTP, PowerFactory, PLECS, RTDS, Typhoon HIL, OPAL-RT, field hardware or utility
model was available or used. pandapower remains only the separate steady-state
AC layer and is not described as EMT.

## Integration boundary

`evidence/gridtwin/results.json` supplies the existing grid-constrained depot and
BESS trajectories. The evidence runner selects the maximum net-import interval
and preserves both components, so loss of BESS support can be evaluated rather
than collapsing the schedule into an unexplained load.

```text
DepotFlux EV schedule + GridTwin BESS schedule
        -> select highest-import operating point
        -> averaged dq electrical scenarios
        -> criteria + violations + fine-step comparison
        -> accept_schedule OR request_reschedule
        -> existing charger_deratings structured-facts contract
        -> remaining-horizon optimizer and human approval boundary
```

The feedback path generates a bounded per-charger derating structure already
accepted by `optimize_real_time`. It does not call the OT gateway, transmit a
setpoint or bypass operator approval.

## Equations and state definitions

The eight states are feeder current `(i_sd, i_sq)`, PCC voltage `(v_d, v_q)`,
aggregate charger current `(i_ld, i_lq)` and BESS-inverter current `(i_bd,
i_bq)`. With the d-axis aligned to the ideal source and `omega = 2*pi*60`, the
source branch follows:

```text
L di_sd/dt = v_sd - R i_sd - v_d + omega L i_sq
L di_sq/dt = v_sq - R i_sq - v_q - omega L i_sd
```

The PCC capacitance applies current balance in the rotating frame. Charger and
BESS currents follow constant-P/Q targets through declared first-order time
constants and nameplate current limits. An equal resistance from each phase to
ground represents the balanced fault. A voltage-dependent shunt clamp limits
the otherwise unbounded ideal R-L-C clearing transient; it is an explicit study
assumption, not a vendor arrester model.

Three-phase power uses the power-invariant dq relation:

```text
P = 1.5 * (v_d i_d + v_q i_q)
Q = 1.5 * (v_q i_d - v_d i_q)
```

PCC voltage and feeder current are reported in per unit on 11 kV line-line and
2 MVA bases. Frequency is a one-cycle estimate from the PCC voltage-vector
angle and is suppressed below 0.50 pu where an angle-derived estimate is not
meaningful. Because the source frequency is fixed, these results do not model
bulk electromechanical frequency response.

## Scenarios and acceptance logic

- Normal load change: the charger target steps from 65% to the schedule-derived
  value.
- Voltage sag: the source is 0.75 pu for 100 ms.
- Three-phase fault: the 3 ohm-per-phase shunt fault lasts 60 ms and clears.
- Inverter trip: the schedule-derived BESS injection falls to zero.

Every case requires finite states, a settled 0.95–1.05 pu post-event voltage,
recovery within 150 ms and settled frequency deviation no greater than 1 Hz.
Scenario-specific retained-voltage, transient-overvoltage and feeder-current
criteria are stored verbatim beside each result in JSON. Generic durations are
also recorded for voltage outside 0.90–1.10 pu, feeder current above 1.20 pu and
valid frequency estimates outside 59–61 Hz.

## Validation

The receiving-end voltage of the two-bus, constant-P/Q operating point with PCC
shunts omitted has an independent quadratic high-voltage solution. The evidence
runner compares that result with the model's iterative phasor initializer at the
same schedule-derived P/Q point and checks the initialized full-model phasor
residual.

The selected 25 microsecond response is compared against the same differential
equations at 6.25 microseconds. Voltage, current, frequency, P and Q waveforms
must meet declared 99th-percentile absolute-error tolerances; minimum voltage,
maximum current and recovery time have separate extrema tolerances. A 50
microsecond case is reported as a deliberately coarse sensitivity point and is
not used for the main metrics.

## Reproduction

```powershell
python -m pip install -r requirements-dev-lock.txt
python scripts/run_grid_dynamics_evidence.py
python -m pytest -q tests/test_gridtwin_dynamics.py tests/test_grid_dynamics_evidence_script.py
```

The run is deterministic apart from the report generation timestamp. It reads
only the committed synthetic schedule evidence and requires no credentials,
network access or licensed simulator.
