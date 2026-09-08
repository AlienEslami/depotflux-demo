# Development and release process

## Change flow

1. Describe one bounded behavior or risk in an issue.
2. Work on a `codex/` feature branch.
3. Record architecture-impacting choices in `docs/adr`.
4. Add tests before declaring the slice complete.
5. Regenerate the OpenAPI contract when public routes change.
6. Run local gates and open a pull request with risks and evidence.
7. Merge only after CI and review pass.

## Definition of done

A product change is complete when:

- public behavior and failure behavior are explicit;
- input validation, authorization and persistence implications are covered;
- unit/integration tests and relevant adverse scenarios pass;
- dashboard lint, type checking and build pass when UI behavior changes;
- migrations upgrade a clean database when the schema changes;
- logs and metrics make failures diagnosable without exposing secrets;
- documentation and the OpenAPI contract are current; and
- the operating boundary and residual risk remain truthful.

## Required gates

```powershell
python -m pytest -q
python scripts/export_openapi.py --check
docker compose --env-file .env.example config --quiet

Push-Location dashboard
npm ci
npm audit
npm run lint
npx tsc --noEmit
npm run build
Pop-Location
```

OT-path changes also require `./scripts/depotflux.ps1 verify` against a clean or
documented local environment.

## Release record

A versioned release records its commit, CI URL, migrations, dependency and image
scan results, SBOMs, local performance context, smoke/isolation/restart evidence,
known limitations and licence decision. Version `0.1.0` remains a demonstrator
release and must not be described as production or field validated.
