# Operator dashboard

This Vinext dashboard is the human approval surface for the industry
demonstrator. It connects to the FastAPI service, submits registered frozen
inputs, polls durable run state, displays validated optimization results, and
records one immutable approve/reject decision per successful candidate.

The interface does not send commands to buses, chargers, or other physical
assets.

## Local development

Start the API and worker from the repository root, then run:

```powershell
npm install
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
