# Job Finder handoff — GridTwin Ops

- Project: **GridTwin Ops: Cyber-Resilient DER, BESS and Electric-Fleet
  Operations Lab**
- Branch/worktree: `codex/gridtwin-ops`
- Canonical evidence: `evidence/gridtwin/results.json` and
  `evidence/gridtwin/results.md`
- Optional solver cross-check: `evidence/gridtwin-gurobi/results.json`
- Gate: passed 2026-09-08; 97 Python tests, OpenAPI drift, dashboard
  lint/type/build and Docker one-command execution verified.

## Verified career evidence

- Extended the existing DepotFlux Pyomo fleet optimizer; did not rebuild the EV
  routing, V2G, tariff, approval, API, dashboard, Docker or OT gateway layers.
- Added pandapower 3.5.4 CIGRE MV AC power flow with the eight-bus depot and a
  500 kWh/250 kW BESS at Bus 11.
- In the documented synthetic 48×30-minute Docker/HiGHS run, cost optimization
  reduced energy cost from 160.070 to 126.301 CAD but retained two
  voltage-violation intervals.
  Grid-constrained BESS dispatch reduced peak site demand from 1,600.0 to
  1,371.5 kW, removed both violations, reduced feeder losses by 5.292 kWh versus
  cost-only dispatch, and added 0.606 CAD modeled cost.
- Preserved a separate optional Gurobi run: it reproduced the 1,371.545 kW
  constrained peak, zero violations and 882.117 kWh BESS throughput; its reported
  combined solve time was 1.647 seconds versus 44.887 seconds for the Docker
  HiGHS run. This is a same-host engineering cross-check, not a controlled solver
  benchmark.
- Added a real `pymodbus` TCP path, false-data injection and unauthorized
  set-point cases, actual gateway credential/range validation, hash-chained audit
  and safe fallback. A TCP-backed integration test observed zero Modbus requests
  for unauthorized and unsafe requests. The four-sample paired fixture scored
  precision/recall/F1 1.0 with zero post-recovery violations; do not generalize
  that tiny-sample score.
- Added APIs, dashboard evidence view, automated tests, one-command Compose
  execution, architecture/threat/risk documents, standards concept mapping and
  requirements-to-test traceability.

## Resume-ready wording (minimum evidence gate passed)

- Built a reproducible pandapower-based CIGRE MV grid twin integrating electric-
  fleet charging and a 500 kWh BESS with AC-validated grid-constrained dispatch.
- Reused a Pyomo fleet scheduler with HiGHS/Gurobi execution and removed two
  modeled half-hour voltage violations while reducing peak site demand 14.3%,
  documenting a 0.606 CAD operating-cost tradeoff against the canonical
  Docker/HiGHS cost-only schedule.
- Implemented `pymodbus` telemetry, adversarial set-point/measurement scenarios,
  constraint-aware detection, audit evidence and safe recovery in a containerized
  software-only energy lab.
- Authored requirements, acceptance criteria, threat/risk artifacts and
  requirements-to-test traceability mapped to IEC 62443 and NIST concepts without
  claiming compliance.

Claim boundary: synthetic/open data and benchmark network only; no utility
employment, production/field deployment, physical control, certification,
standards compliance or proprietary simulator experience. Do not publish or
push without Ali's explicit approval and an owner-approved licence.
