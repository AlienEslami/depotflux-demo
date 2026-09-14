# GridTwin evidence and claim boundary

## Evidence currently implemented

- Open CIGRE MV AC feeder in pandapower 3.5.4 with the retained eight-bus EV
  depot and one 500 kWh/250 kW BESS connected at Bus 11.
- Measured uncontrolled, cost-optimized and grid-constrained 48×30-minute runs.
- Real Modbus/TCP socket exchange using `pymodbus` 3.15.0 against a deterministic
  software PLC.
- False-data injection and unauthorized set-point cases with constraint-aware
  detection, actual gateway credential/range validation, zero observed Modbus
  requests after denial, hash-chained audit and validated fallback.
- Versioned API routes, dashboard panel, tests, Compose command, architecture,
  threat/risk and requirements traceability artifacts.
- A schedule-linked, balanced synchronous-dq averaged electromagnetic-transient
  model with source/feeder, charger and BESS current dynamics; four deterministic
  disturbance cases; analytical and finer-step validation; and rescheduling
  feedback. This is not switching-level EMT or licensed-tool evidence.

## Exact statements defensible after the complete verification gate passes

1. Built a reproducible pandapower-based CIGRE MV distribution-grid twin that
   integrates an existing electric-bus depot schedule and a 500 kWh battery,
   comparing uncontrolled, cost-optimized and grid-constrained operation.
2. Reused a Pyomo fleet scheduler with open HiGHS and optional Gurobi execution,
   and added AC power-flow validation that
   reduced the measured site peak from 1,600.0 to 1,371.5 kW and removed two
   half-hour voltage-violation intervals in the documented synthetic case, with
   a 0.606 CAD modeled cost tradeoff in the canonical Docker/HiGHS run.
3. Implemented a real `pymodbus` TCP telemetry/command path, false-data and
   unauthorized set-point scenarios, constraint-aware detection, hash-chained
   audit evidence and safe schedule recovery in a containerized software lab.
4. Authored stakeholder requirements, acceptance criteria, interface contracts,
   an architecture/threat model, risk register and requirements-to-test
   traceability, with safeguards mapped to IEC 62443 concepts, NIST CSF 2.0 and
   NIST SP 800-82 Rev. 3 without claiming compliance.
5. Added a simulated averaged grid-dynamics study linking the retained EV/BESS
   schedule to load-change, voltage-sag, cleared-fault and inverter-trip cases,
   with explicit criteria, analytical operating-point validation and fixed-step
   convergence against a finer reference.

Measured-result wording applies only to experiment
`gridtwin-cigre-mv-depot-a-8-v1` and the committed
`evidence/gridtwin/results.json` artifact. The
detector's perfect score is not suitable as a resume improvement claim because
it is based on only two attack and two clean deterministic samples.

## Statements not supported

This project does not support claims of utility/ISO/RTO employment, control-room
operation, field commissioning, physical BESS/charger integration, production
deployment, functional safety, independent cyber assessment, general detector
accuracy, IEC/NIST compliance or certification, an achieved IEC 62443 security
level, or experience operating CYME/PSS®E/PSCAD/PowerFactory/EMS/DMS/SCADA.
The work also does not support claims of MATLAB/Simulink, Simscape Electrical,
Specialized Power Systems, EMTP, PLECS, RTDS, Typhoon HIL or OPAL-RT experience,
nor protection settings, switching-level EMT, equipment duty or grid-code
compliance.

## Publication and licence gate

The owner selected the MIT License on 2026-09-14, matching the retained upstream,
and explicitly authorized publication. This does not remove the need to review
the exact publication candidate, monitor CI and disclose remaining limitations.
The bounded secret/history, dependency/SBOM, advisory and claims reviews are
recorded in `docs/GRIDTWIN_RELEASE_HARDENING_REPORT.md`.
