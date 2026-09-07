# DepotFlux OT security extension

DepotFlux connects its human-approved optimization workflow to a synthetic
operational-technology boundary. It now sends real Modbus/TCP frames over an
isolated software network to a simulated PLC. It has no physical I/O adapter,
does not publish the PLC or gateway port to the host, and continues to report
`direct_asset_control=false`.

## Implemented path

An operator selects one interval from a successful, deterministically validated
and immutably approved schedule. The API derives the power value and checks a
separate control credential, result digest, interval and site envelope. The
internal gateway checks freshness, expiry, replay and range, then performs an
FC10 write and FC03 readback through a bounded-timeout client. Both accepted and
rejected attempts are persisted with correlation IDs and structured events.

The legacy `/control-simulations` endpoint remains for compatibility and only
creates a frame artifact. The implemented TCP path is:

```text
POST /api/v1/runs/{run_id}/dispatch-simulations
```

The separate emergency drill path accepts a reason and `X-Emergency-Key`, then
writes zero import/export with an explicit safe-state mode. An ordinary zero
dispatch uses normal mode, preventing misleading evidence.

## Local use

```powershell
./scripts/start_ot_lab.ps1
./scripts/run_ot_evidence.ps1
```

The first command creates local ephemeral secrets under ignored `.demo/`, builds
the seven-service Compose lab, applies migrations and waits for health. The
second runs protocol/API tests, an end-to-end optimization/approval/dispatch
smoke scenario, network-isolation assertions and evidence export.

Design, tests, claim boundaries and response guidance are maintained in:

- `OT_NETWORK_ARCHITECTURE.md`
- `OT_ASSURANCE_CASE.md`
- `OT_PROTOCOL_TEST_PLAN.md`
- `OT_INCIDENT_RESPONSE.md`
- `OT_DEMO_SCRIPT.md`

Passing the evidence gate supports only a portfolio claim about designing and
testing a secure, auditable, software-only OT integration prototype. It does not
support claims of production deployment, field commissioning, compliance,
certification, an achieved IEC 62443 security level, or control of real charging
equipment.
