# DepotFlux

DepotFlux is a software-only electric-fleet energy operations demonstrator. It
runs day-ahead and remaining-horizon charging optimization, requires a distinct
human approval role, and carries approved schedule intervals through a
policy-enforced synthetic Modbus/TCP path. Every accepted and rejected action is
correlated and persisted for review.

The project is deliberately bounded: it does not connect to buses, chargers,
utility systems, or physical controllers. It is an engineering demonstrator,
not a production control or safety system.

## What the software demonstrates

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
        -> synthetic OT gateway -> Modbus/TCP PLC simulator
        -> structured security events -> read-only monitor
```

Compose separates the operator, industrial DMZ, supervisory, control and
monitoring networks. The PLC and gateway are not published on host ports. Only
the gateway shares the control network with the PLC.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
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
