# GridTwin Ops

**GridTwin Ops: Cyber-Resilient DER, BESS and Electric-Fleet Operations Lab**
extends the existing DepotFlux software demonstrator with an open CIGRE MV
distribution-grid twin, a 500 kWh/250 kW BESS, AC-validated dispatch and paired
cyber-attack/recovery evidence. It reuses DepotFlux's Pyomo fleet optimizer,
FastAPI lifecycle, dashboard, approval boundary, Docker networks, tests and
synthetic PLC.

The project is deliberately bounded: it does not connect to buses, chargers,
utility systems, physical batteries or physical controllers. It is a synthetic
engineering portfolio demonstrator, not a production control, protection or
safety system. Safeguards are mapped to selected standards concepts; no
compliance or certification is claimed.

## Measured minimum-evidence result

Experiment `gridtwin-cigre-mv-depot-a-8-v1` uses pandapower 3.5.4, the open
CIGRE MV benchmark at a documented 0.55 load scale and the retained eight-bus
DepotFlux fixture. The table is the canonical one-command Docker result using
the credential-free HiGHS default.

| Scenario | Cost (CAD) | Export revenue (CAD) | Peak site (kW) | Feeder losses (kWh) | Voltage violation intervals | BESS throughput (kWh) |
|---|---:|---:|---:|---:|---:|---:|
| Uncontrolled | 160.070 | 0.000 | 1,600.0 | 2,105.033 | 2 | 0.000 |
| Cost optimized | 126.301 | 55.962 | 1,600.0 | 2,112.639 | 2 | 801.053 |
| Grid constrained | 126.907 | 55.962 | 1,371.5 | 2,107.347 | 0 | 882.117 |

The grid constraint removed two half-hour undervoltage intervals and reduced
the site peak by 228.455 kW versus cost-only operation, reduced modeled feeder
losses by 5.292 kWh and added 0.606 CAD modeled cost. No thermal violations
occurred in any case. The deterministic
attack fixture detected a forged voltage value, exercised the real gateway
credential gate, denied an unauthorized unsafe set-point with zero observed
Modbus requests and recovered with zero remaining violations.
See [measured results](evidence/gridtwin/results.md), the
[schedule comparison](evidence/gridtwin/schedule-comparison.svg) and the
[milestone report](docs/GRIDTWIN_MILESTONE_1_REPORT.md). The
[claim boundary](docs/GRIDTWIN_CLAIM_BOUNDARY.md) governs all wording. An optional local academic
Gurobi 13.0.2 run is preserved separately in
[`evidence/gridtwin-gurobi/`](evidence/gridtwin-gurobi/); the
[solver comparison](docs/GRIDTWIN_SOLVER_COMPARISON.md) explains the measured
alternate-optimum differences.

## One-command GridTwin demo

Requirements: Windows PowerShell, Docker Desktop and Docker Compose.

```powershell
./scripts/depotflux.ps1 gridtwin
```

This builds/starts the existing seven-service lab, applies migrations, runs the
three grid scenarios plus the paired security cases, and writes JSON, Markdown,
SVG and hash-chained audit evidence under `evidence/gridtwin/`. It uses only
bundled synthetic data and the packaged open benchmark; no private credentials,
cloud service or external data download is needed at runtime.

For an optional faster local run with the owner's installed academic Gurobi
licence:

```powershell
$env:DA_SOLVER_ORDER='gurobi,appsi_highs,highs'
$env:GRIDTWIN_SOLVER_ORDER='gurobi,appsi_highs,highs'
python scripts/run_gridtwin_evidence.py --output evidence/gridtwin-gurobi
```

## What the software demonstrates

- Balanced AC power flow on an open CIGRE MV feeder with named EV/BESS assets.
- Uncontrolled, cost-only and grid-constrained schedules with economic,
  electrical, battery and timing metrics.
- A real `pymodbus` FC10/FC03 TCP path, false-data injection, unauthorized
  set-point denial, physics-aware detection, safe recovery and hash-chained audit.
- Versioned FastAPI contracts and a typed React/TypeScript operations dashboard.
- Durable asynchronous optimization with PostgreSQL, SQLAlchemy and Alembic.
- Idempotent run submission, immutable approvals and explicit lifecycle states.
- Operator, approver, auditor and administrator service accounts with
  role-separated Bearer keys.
- A real TCP exchange between an OT gateway and deterministic Modbus simulator.
- Five logical network zones with a gateway-only PLC conduit.
- Structured JSON logs, request correlation IDs and Prometheus-format metrics.
- Verified application-data backup/restore, deterministic seeding and restart
  recovery checks.
- Unit, integration, adverse-path, Compose, network-isolation and performance
  evidence in CI and the local validation workflow.

## Quick start

Requirements: Windows PowerShell, Docker Desktop and Docker Compose.

```powershell
./scripts/depotflux.ps1 start
./scripts/depotflux.ps1 credentials
```

Open `http://127.0.0.1:3000`. Paste the operator role key into the session-only
access field. Switch to the approver key when recording a decision; use the
auditor key for read-only review. The start command builds seven services,
applies migrations to an empty PostgreSQL database, validates health and queues
a deterministic starter run.

The services bind only to loopback:

- Dashboard: `http://127.0.0.1:3000`
- API and OpenAPI UI: `http://127.0.0.1:8000/docs`
- API metrics: `http://127.0.0.1:8000/metrics`
- Security summary: `http://127.0.0.1:9100/metrics/security-summary`

Stop the application without deleting data:

```powershell
./scripts/depotflux.ps1 stop
```

## Product workflow

1. An operator queues a registered, hash-verified optimization input.
2. The worker claims the run and persists a validated solver result.
3. An approver records an immutable approval or rejection bound to that result
   digest.
4. An operator selects an approved run and interval. The server derives the
   setpoint; the browser cannot submit an arbitrary normal command.
5. The policy authority and gateway reject invalid credentials, changed hashes,
   missing approvals, stale/future/replayed commands and out-of-range values.
6. The gateway exchanges FC10 and FC03 frames with the synthetic PLC.
7. An auditor follows the correlation ID through the run, decision, policy,
   frame and controller-response evidence.

## Architecture

```text
React dashboard
    -> FastAPI policy and workflow service
        -> PostgreSQL evidence store
        -> optimization worker -> Pyomo / HiGHS
        -> grid evidence -> pandapower CIGRE MV -> EV depot + BESS
        -> synthetic OT gateway -> Modbus/TCP PLC simulator
        -> structured security events -> read-only monitor
```

Compose separates the operator, industrial DMZ, supervisory, control and
monitoring networks. The PLC and gateway are not published on host ports. Only
the gateway shares the control network with the PLC.

See [the GridTwin architecture](docs/GRIDTWIN_ARCHITECTURE.md),
[requirements traceability](docs/GRIDTWIN_REQUIREMENTS_TRACEABILITY.md),
[threat model and risk register](docs/GRIDTWIN_THREAT_MODEL.md),
[standards concept mapping](docs/GRIDTWIN_STANDARDS_MAPPING.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/OT_ASSURANCE_CASE.md](docs/OT_ASSURANCE_CASE.md) for design and assurance
details.

## Application lifecycle

```powershell
# Current service state
./scripts/depotflux.ps1 status

# Queue the deterministic starter run again (idempotent)
./scripts/depotflux.ps1 seed

# Run tests, smoke scenarios, isolation, benchmark and restart checks
./scripts/depotflux.ps1 verify

# Back up application data under .demo/backups
./scripts/depotflux.ps1 backup

# Restore one verified backup; explicit acknowledgement is required
./scripts/depotflux.ps1 restore -BackupPath .demo/backups/depotflux-TIMESTAMP.json -Force

# Remove only the synthetic database volume and rebuild the seeded lab
./scripts/depotflux.ps1 reset -Force
```

Local credentials, databases, backups and generated evidence remain ignored
under `.demo/`.

## Development

Python 3.12 and Node.js 24 are used by CI.

```powershell
python -m pip install -r requirements-dev-lock.txt
python -m pytest -q
python scripts/export_openapi.py --check

Push-Location dashboard
npm ci
npm audit
npm run lint
npx tsc --noEmit
npm run build
Pop-Location
```

The committed API contract is [openapi/depotflux-v1.json](openapi/depotflux-v1.json).
Changes to public routes must regenerate it with `python scripts/export_openapi.py`.

## Repository structure

```text
aggregator_demo/           application, persistence, policy and protocol code
  demo_data/               immutable synthetic fleet inputs
  optimization/            mathematical day-ahead and real-time cores
dashboard/                 React/TypeScript operator application
migrations/                ordered PostgreSQL/SQLite schema migrations
openapi/                    committed versioned API contract
scripts/                    lifecycle, validation and evidence commands
detections/                 example Sigma and KQL security analytics
tests/                      product-focused automated tests
docs/                       architecture, operations, ADRs and assurance case
```

The paper workbooks, experimental matrices and orchestration exports are kept in
the preserved research branch and are intentionally outside this software
product boundary. See [docs/PRODUCT_BOUNDARY.md](docs/PRODUCT_BOUNDARY.md).

## Current limitations

- The CIGRE snapshot is balanced and synthetic; it is not calibrated to a real
  feeder, protection system, load profile or field measurement.
- Grid-constrained dispatch retains the EV MILP schedule and optimizes the BESS
  against a snapshot-specific AC-derived import envelope; it is not full AC OPF.
- Detection metrics use two clean and two attack samples and do not establish
  general precision, recall or operational detection performance.
- Role keys are local service-account credentials, not an external OIDC/IAM
  integration.
- Replay state in the gateway is process-local.
- Modbus/TCP is unauthenticated at the protocol layer.
- Docker networks demonstrate zones and conduits but are not industrial
  firewalls.
- Audit evidence is mutable relational data, not signed or WORM storage.
- The PLC is a deterministic simulator, not hardware-in-the-loop or a grid
  digital twin.
- Horizontal scaling, production high availability and field commissioning are
  outside the current release.

## Security and licence

Read [SECURITY.md](SECURITY.md) before reporting a vulnerability or operating
the lab. The repository does not yet grant a software or documentation licence;
public visibility alone would not grant reuse rights. A licence will be added
only after the repository owner confirms the intended terms.
