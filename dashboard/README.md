# DepotFlux Operations

DepotFlux Operations is the human approval surface for the industry
demonstrator. It connects to the FastAPI service, submits registered frozen
inputs, polls durable run state, displays validated optimization results,
preserves simulated disruption notices, compares remaining-horizon candidates
with approved baselines, and records one immutable approve/reject decision per
successful candidate.

The interface does not send commands to buses, chargers, or other physical
assets.

When the Compose lab is running, paste one key from
`./scripts/depotflux.ps1 credentials` into the session-only role access field.
Operator, approver, auditor and administrator actions are enforced by the API;
the dashboard does not store credentials in local storage or its build output.

## Local development

Start the API and worker from the repository root, then run:

```powershell
npm ci
npm run dev
```

The default API origin is `http://127.0.0.1:8000`. Copy `.env.example` to
`.env.local` and change `NEXT_PUBLIC_API_BASE_URL` when the API is hosted at a
different origin. Add the dashboard origin to `DEMO_ALLOWED_ORIGINS` in the API
environment.

## Validation

```powershell
npm audit
npm run lint
npx tsc --noEmit
npm run build
```
