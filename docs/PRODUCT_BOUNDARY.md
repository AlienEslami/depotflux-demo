# Product boundary

## Decision

The `codex/software-v0.1` branch is the software product line for DepotFlux. It
contains the executable application, immutable synthetic fixtures, schema
migrations, product tests, lifecycle automation, machine-readable API contract,
security analytics and operational documentation.

The following material is intentionally outside the product line:

- manuscript text and reviewer-response material;
- paper result workbooks and experiment matrices;
- research-only orchestration and prompt exports;
- exploratory and reproduction scripts;
- private or machine-specific input workbooks; and
- tests that exercise only the removed research harness.

Those files remain recoverable from `codex/industry-demonstrator` and earlier Git
history. Nothing was irreversibly deleted when the product boundary was created.

## Included runtime

The runtime dependency path is:

```text
dashboard -> FastAPI -> repositories -> PostgreSQL
                    -> optimization worker -> packaged optimization cores
                    -> OT policy -> gateway -> synthetic PLC
                    -> security events -> monitoring endpoint
```

Only `aggregator_demo`, its bundled JSON fixtures, migrations and the dashboard
are copied into runtime images. Research directories cannot enter an image
accidentally because the Dockerfile uses an explicit allowlist.

## Release rule

A release is built only from this product line after its Python, dashboard,
OpenAPI, Compose, smoke, isolation, benchmark and restart-recovery gates pass.
Repository history and licence choices remain separate owner decisions.
