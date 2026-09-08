# WP-SW-01: DepotFlux software productization

## Objective

Create a reviewable software product line from the industry demonstrator and
exercise the engineering lifecycle needed to operate, change and release it.

## Delivery record

| Slice | Acceptance evidence | Status |
|---|---|---|
| Product boundary | Runtime-only branch content and allowlisted image build | Implemented |
| Install and operate | One lifecycle command, validated configuration and deterministic seed | Implemented |
| Application workflow | Versioned API, typed dashboard, role separation and consistent errors | Implemented |
| Operations | Logs, correlation, metrics, backup/restore, benchmark and restart recovery | Implemented |
| Development process | ADRs, issue/PR templates, CI gates, changelog and release checklist | Implemented |
| v0.1 release | Clean-clone verification, owner licence decision and release tag | Pending owner decision |

## Validation snapshot

The 2026-09-07 local candidate review produced the following evidence:

- 83 product tests passed;
- the Python wheel built and imported from a separate installation directory;
- Bandit, `pip-audit` and `npm audit` passed;
- dashboard lint, TypeScript checking and production build passed;
- the seven-service Compose lab rebuilt, started and completed its authenticated
  dispatch/rejection and network-isolation scenarios;
- 200 authenticated concurrent reads completed with zero errors and 69.784 ms
  p95 latency on the review host;
- API and worker restart preserved and reloaded an existing run; and
- a content-digested application backup restored successfully with all services
  returning to their expected running/healthy states.

Generated run evidence is intentionally kept under ignored `.demo/evidence`.

## Exit criteria

- Fresh local startup reaches healthy state and produces a deterministic run.
- Operator credentials cannot approve; approver credentials cannot submit work.
- Backup integrity and transactional restore are tested.
- The API contract is generated and checked in CI.
- All product tests, dashboard checks and Compose evidence pass.
- No physical control or production-readiness claim is introduced.
