# Software architecture

## Context

DepotFlux is a local decision-support application for a synthetic electric-bus
depot. An operator requests an optimization, a separate approver accepts or
rejects its immutable result, and an operator can dispatch only a server-derived
interval through the simulated OT path. Auditors can reconstruct the outcome.

No component is authorized to control a physical asset.

## Containers and responsibilities

| Component | Responsibility | Durable state |
|---|---|---|
| Dashboard | Operator, approval and audit workflow | None; keys remain in page memory |
| API | Contracts, RBAC, workflow policy and evidence queries | PostgreSQL through repositories |
| Worker | Claims queued runs and executes Pyomo/HiGHS optimization | PostgreSQL run lifecycle and result |
| Database | Runs, notices, approvals, dispatch attempts and events | Named local volume |
| OT gateway | Independent command freshness, replay and envelope policy | Process-local replay cache |
| PLC simulator | Deterministic FC03/FC10 register model | Process memory |
| Security monitor | Read-only aggregation of structured events | None |

## Trust boundaries

Compose models enterprise/operator, industrial DMZ, supervisory/EMS,
control/PLC and monitoring zones. Only the gateway joins the control network
with the PLC. The API, worker and monitor are tested to ensure that they cannot
resolve or connect to the controller.

Human-facing access uses four fixed local service accounts: operator, approver,
auditor and administrator. Keys are independently generated and compared in
constant time. The control, emergency and gateway credentials are separate from
those human workflow roles. This demonstrates least privilege and separation of
duties without claiming production IAM.

## Consistency and recovery

- Run creation supports idempotency keys and request fingerprints.
- Workers claim durable rows and recover abandoned work after a stale heartbeat.
- Approvals are unique per run and bound to the persisted result digest.
- Dispatch evidence is written for accepted, rejected and failed attempts.
- Alembic owns deployed schema changes; automatic table creation is disabled in
  Compose.
- Application backups are content-digested and restored inside one database
  transaction after explicit acknowledgement.
- API and worker restart recovery is exercised by the evidence workflow.

## Observability

The API assigns or validates one UUID correlation ID per request, returns it in
`X-Correlation-ID`, records bounded route/status metrics and emits structured
JSON logs. The worker logs run claim and terminal state. `/metrics` exposes
request totals, cumulative latency and process uptime in Prometheus text format.

## Public contract

FastAPI generates the OpenAPI contract committed as
`openapi/depotflux-v1.json`. CI fails if the contract is stale. Breaking changes
require a new API version or an explicit release decision.
