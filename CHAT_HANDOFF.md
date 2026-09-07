# DepotFlux development handoff

Use this file to brief another coding chat or agent. The project is located at:

```text
C:\Users\alien\Documents\ChatGPT\Agentic Aggregator\Agentic-Aggregator-Python-Workflow
```

Repository: `https://github.com/AlienEslami/depotflux-demo`
Development branch: `codex/industry-demonstrator`

## Objective

Continue developing **DepotFlux**, an interview-ready electric-fleet operations
and OT cybersecurity demonstrator built around the repository's existing
optimization research.

DepotFlux demonstrates how a fleet-energy schedule can move from deterministic
optimization through immutable human approval and security policy to a
synthetic Modbus/TCP controller, with network segmentation, negative tests,
structured detections and correlated audit evidence.

## Non-negotiable boundary

- The system is synthetic and software-only.
- Never connect it to a physical PLC, charger, bus, building controller, utility
  interface or field network.
- Preserve `direct_asset_control=false`.
- Do not describe it as production-ready, compliant, certified, field-tested,
  functionally safe, or as achieving an IEC 62443 security level.
- Standards language must say “mapped to”, “aligned with concepts from”, or
  equivalent limited wording.
- Do not publish, change remote infrastructure, or edit résumés unless the user
  explicitly authorizes that specific action.
- Inspect `git status`, recent history and current tests before changing files.
  Preserve unrelated user changes.

## Implemented architecture

```text
Operator dashboard
    -> FastAPI policy authority
    -> internal supervisory gateway
    -> synthetic Modbus/TCP PLC

Optimization worker -> PostgreSQL evidence store
API -> structured security events -> monitoring service
```

`compose.yaml` implements five logical networks:

1. enterprise/operator;
2. industrial DMZ;
3. supervisory/EMS;
4. control/PLC; and
5. monitoring.

Only the dashboard, API and read-only monitor bind host loopback ports. The PLC
and gateway are not host-exposed. Only the gateway shares the control network
and the PLC accepts only the gateway's fixed control-network address.

## Implemented security behavior

The normal API accepts an approved run and interval, not an arbitrary setpoint.
It derives the setpoint from the stored result and enforces:

- separate control credential;
- successful run state;
- immutable operator approval;
- approval/result SHA-256 binding;
- deterministic validation;
- interval-in-horizon and finite/range checks; and
- modeled site-capacity limits.

The gateway additionally enforces issued/expiry time, future-skew, replay,
protocol range, response validation, bounded timeout/retry and heartbeat checks.
Transport ambiguity triggers a best-effort zero-power safe-state attempt.

The emergency endpoint uses a different credential and reason. Its protocol
command uses explicit safe-state mode; a normal zero-power dispatch remains a
normal active dispatch.

Both accepted and rejected attempts preserve actor, run/result hash, command
UUID, correlation UUID, reason, timestamps, policy checks, Modbus frames and
controller response when available.

## Synthetic register map

| Address | Meaning |
|---:|---|
| 100 | Import setpoint magnitude, 0.1 kW/count |
| 101 | Export setpoint magnitude, 0.1 kW/count |
| 102 | Command mode: 0 dispatch, 1 safe state |
| 110 | Signed measured site power |
| 120 | Controller state: ready, active or safe state |
| 121 | Alarm bitfield |
| 130 | Heartbeat counter |

The implementation uses Modbus/TCP FC10 writes and FC03 readback over a real TCP
socket between software containers. It has no physical I/O implementation.

## Important files

- `README.md` — project entry point and local start instructions.
- `compose.yaml` — segmented seven-service lab.
- `aggregator_demo/app.py` — public API and operating boundary.
- `aggregator_demo/dispatch_repository.py` — policy and evidence persistence.
- `aggregator_demo/ot_gateway.py` — freshness, replay, retry and heartbeat gate.
- `aggregator_demo/modbus_tcp.py` — protocol codec/client.
- `aggregator_demo/plc_simulator.py` — deterministic synthetic controller.
- `aggregator_demo/security_monitor.py` — read-only event summary.
- `dashboard/app/page.tsx` — operator and OT evidence dashboard.
- `migrations/versions/0007_add_ot_dispatch_evidence.py` — evidence schema.
- `tests/test_modbus_tcp_gateway.py` — protocol/gateway adverse scenarios.
- `tests/test_ot_dispatch_api.py` — approval-to-controller integration tests.
- `detections/` — illustrative Sigma and KQL rules.

## Assurance and interview documents

- `docs/OT_NETWORK_ARCHITECTURE.md`
- `docs/OT_ASSURANCE_CASE.md`
- `docs/OT_PROTOCOL_TEST_PLAN.md`
- `docs/OT_INCIDENT_RESPONSE.md`
- `docs/OT_INDUSTRY_DEMONSTRATOR_WORK_PACKAGE.md`
- `docs/PORTFOLIO_CASE_STUDY.md`
- `docs/OT_DEMO_SCRIPT.md`
- `docs/PUBLIC_RELEASE_REVIEW.md`

The assurance mappings use the official NIST SP 800-82 Rev. 3, NIST CSF 2.0,
IEC 62443 concept descriptions and MITRE ATT&CK for ICS technique pages. They do
not assert compliance or certification.

## Reproduction commands

Requirements: Python 3.12+, Windows PowerShell, Node 22+ and Docker Desktop.

```powershell
./scripts/start_ot_lab.ps1
./scripts/run_ot_evidence.ps1
```

The start script creates reusable local secrets in ignored `.demo/ot-lab.env`,
builds the lab, applies migrations and waits for health. The evidence script
runs focused protocol/API tests, the full Compose smoke flow and network
isolation checks.

Manual regression commands:

```powershell
python -m pytest -q

Push-Location dashboard
npm run lint
npx tsc --noEmit
npm run build
Pop-Location
```

## Last verified state

- 229 Python tests passed; one pre-existing Starlette TestClient deprecation
  warning remains.
- Dashboard lint, TypeScript check and production build passed. The build reports
  a non-blocking large JavaScript chunk warning.
- All Docker images built.
- An empty PostgreSQL database migrated from revision 0001 through 0007.
- All seven Compose services became healthy/running.
- End-to-end optimization, approval, valid dispatch, replay rejection, stale
  rejection, invalid-key rejection, horizon rejection and emergency safe state
  passed.
- Network verification proved the API, worker and monitor cannot resolve the
  PLC, while the gateway can connect.
- Secret-pattern scan and `git diff --check` passed.

## Demonstrated adverse scenarios

Invalid/missing credential, unapproved or rejected result, approval-hash
mismatch, replay, stale/future command, out-of-range setpoint, outside-horizon
interval, direct PLC access, register scan, controller loss, frozen heartbeat and
emergency safe-state activation.

## Known limitations

Authentication uses demonstrator shared secrets and a user-supplied operator
header. Replay state is single-process memory. Modbus itself is unauthenticated.
Docker networks are not industrial firewalls. Evidence is not signed or WORM.
There is no real process model, hardware-in-the-loop, safety analysis, high
availability, penetration test, live SIEM validation or field commissioning.

## Recommended next stage

Run the independent release gate in `docs/PUBLIC_RELEASE_REVIEW.md`. The most
valuable engineering follow-ups are durable/shared replay protection, stronger
identity/RBAC, authenticated service-to-service transport, rate limiting,
signed evidence exports, SBOM/vulnerability review, browser accessibility QA,
and an independent threat-model/code review.

Keep IEC 61850, Microsoft Sentinel integration, DNP3/OPC UA, power-flow
simulation and Kubernetes explicitly labeled as future backlog until implemented
and verified.
