# Milestone 1 report — minimum evidence sprint

Status: **passed on 2026-09-08**. This is synthetic, software-only engineering
evidence and does not establish field readiness, safety, certification or
standards compliance.

## Implemented

- Reused the DepotFlux EV MILP, fixture registry, API lifecycle, dashboard,
  approval boundary, Docker lab, PLC simulator and test architecture.
- Added pandapower's open CIGRE MV feeder with existing loads scaled to 0.55;
  connected the named EV depot and one 500 kWh/250 kW BESS at Bus 11.
- Evaluated uncontrolled, cost-optimized and AC-envelope-constrained schedules
  over the same 48 half-hour intervals.
- Added a real `pymodbus` FC10/FC03 client path, two deterministic attack cases,
  constraint-aware detection, actual gateway credential/range validation, safe
  recovery and a SHA-256 previous-record audit chain. The TCP-backed integration
  probe observes zero Modbus requests for unauthorized and unsafe commands.
- Added versioned API routes, a dashboard evidence panel, one-command Docker
  execution, architecture/threat/risk/requirements/traceability artifacts and
  IEC 62443/NIST concept mappings with explicit non-compliance wording.

## Measured canonical result

Command: `./scripts/depotflux.ps1 gridtwin` (Docker, HiGHS 1.15.1).

| Scenario | Cost (CAD) | Revenue (CAD) | Peak (kW) | Feeder losses (kWh) | Voltage / thermal violation intervals | BESS throughput (kWh) | Reported combined solve time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Uncontrolled | 160.070 | 0.000 | 1,600.000 | 2,105.033 | 2 / 0 | 0.000 | 0.000 |
| Cost optimized | 126.301 | 55.962 | 1,600.000 | 2,112.639 | 2 / 0 | 801.053 | 44.904 |
| Grid constrained | 126.907 | 55.962 | 1,371.545 | 2,107.347 | 0 / 0 | 882.117 | 44.887 |

Against cost-only operation, the grid-constrained schedule reduced peak demand
by 228.455 kW (14.28%), removed two half-hour voltage-violation intervals,
reduced modeled feeder losses by 5.292 kWh and added 0.606 CAD modeled cost.
All scenarios served the required EV energy; no thermal violation occurred.

The attack fixture contained two attack and two clean samples. It produced two
true positives, two true negatives, no false positives/negatives, precision,
recall and F1 of 1.0, a `gateway_authentication_failed` decision with zero
observed Modbus writes/reads for the unauthorized set-point, zero remaining
violations after recovery and a valid audit hash chain. Those
scores describe only this four-sample deterministic fixture.

The Docker evidence run took 75.966 seconds. The in-process authenticated
metadata endpoint measured p50 4.094 ms and p95 5.676 ms over 30 requests. A live
request to the deployed container returned HTTP 200. These latency observations
are not load tests.

## Optional solver cross-check

The separate local Gurobi 13.0.2 academic-licence run passed the same minimum
gate in 33.336 seconds. It reproduced the constrained 126.907 CAD cost,
1,371.545 kW peak, zero grid violations and 882.117 kWh BESS throughput. Its
reported constrained combined solve time was 1.647 seconds. Solver-dependent
alternate-optimum differences are documented in
`docs/GRIDTWIN_SOLVER_COMPARISON.md`; this is not a controlled solver benchmark.

## Verification

- Pre-change baseline: 83 Python tests passed.
- Post-change regression: 97 passed in 246.81 seconds; one upstream Starlette
  TestClient deprecation warning.
- Combined line/branch coverage: 73.681%; statement coverage 77.863%; branch
  coverage 57.156%.
- OpenAPI drift check: passed.
- Dashboard lint, TypeScript no-emit check and production build: passed. Build
  retained a non-blocking >500 kB chunk advisory and Vinext route-classification
  note.
- Runtime visual QA: GridTwin evidence card and operating boundary rendered at
  `http://127.0.0.1:3000` with no browser console warnings; role-protected data
  controls remained locked without a local access key.
- Docker: seven services running after the command; five health-checked services
  reported healthy, while dashboard and worker (no Compose healthcheck) were
  running. Evidence generation completed with all three minimum-gate flags true.

## Reproducible now

- A clean local clone with Docker Desktop and PowerShell can create the isolated
  `gridtwin-ops-lab` resources and regenerate the canonical JSON, Markdown, SVG
  and audit artifacts with one command.
- Python tests regenerate JUnit and coverage reports via
  `./scripts/verify_gridtwin.ps1`; the same script verifies OpenAPI and dashboard
  builds.
- Bundled synthetic data and the packaged open feeder require no runtime data
  download or private credential. Generated local role/database keys stay in the
  ignored `.demo/` directory.
- The Gurobi result is reproducible only where a suitable local licence exists;
  Docker and CI remain credential-free through HiGHS.

## Remaining gaps

- Forecast evaluation, market backtesting/P&L attribution, joint EV+BESS
  grid-constrained optimization or AC OPF, N-1 cases, IEC 61850 artifacts and a
  four-attack GridTwin scorecard remain in the broader four-week brief.
- Current AC validation is balanced steady-state power flow with a scalar
  hosting envelope; it is not protection, dynamic/stability, harmonic,
  unbalanced, state-estimation or field validation.
- Docker networks are illustrative zones, not industrial firewalls; telemetry is
  not authenticated on the Modbus wire; durable replay coordination, external
  IAM, signed/WORM evidence, SIEM exercise and independent review remain open.
- Public release remains blocked on owner-selected repository licence,
  secret/history scan, dependency licence/SBOM/CVE review and final claims review.
- Existing dashboard dependencies report four high-severity `npm audit` findings;
  no breaking force-upgrade was applied during this bounded sprint.

## Exact resume statements now defensible

1. Built a reproducible pandapower-based CIGRE MV distribution-grid twin that
   integrates an existing electric-fleet schedule and a 500 kWh battery, and
   compares uncontrolled, cost-optimized and grid-constrained operation.
2. Reused a Pyomo fleet scheduler with HiGHS/Gurobi execution and added AC
   power-flow validation that reduced modeled site peak from 1,600.0 to 1,371.5
   kW and removed two half-hour voltage-violation intervals in the documented
   synthetic Docker case, with a 0.606 CAD modeled cost tradeoff.
3. Implemented a real `pymodbus` TCP telemetry/command path, false-data and
   unauthorized set-point scenarios, constraint-aware detection, hash-chained
   audit evidence and safe schedule recovery in a containerized software lab.
4. Authored stakeholder requirements, acceptance criteria, interface contracts,
   an architecture/threat model, risk register and requirements-to-test
   traceability, mapping safeguards to IEC 62443, NIST CSF 2.0 and NIST SP
   800-82 Rev. 3 concepts without claiming compliance.

Do not broaden these statements to utility employment, production/field
deployment, physical control, general detector accuracy, certification or
standards compliance.
