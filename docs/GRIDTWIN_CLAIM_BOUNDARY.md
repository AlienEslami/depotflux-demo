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

## Publication and licence gate

No push, public release, research disclosure or cloud deployment is authorized.
The repository still has no owner-approved public licence. Before publication,
the owner must select a licence and complete the existing public-release review,
dependency/SBOM review, secret/history scan and claims review.
