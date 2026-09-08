# Contributing

Thanks for helping improve DepotFlux. Keep changes within the documented
synthetic, software-only boundary and do not add real credentials, personal
data, private infrastructure identifiers or proprietary operational data.

## Development checks

Use Python 3.12 or newer and Node.js 24 for the dashboard.

```powershell
python -m pip install -r requirements-dev-lock.txt
python -m pytest -q
python scripts/export_openapi.py --check

Set-Location dashboard
npm ci
npm audit
npm run lint
npx tsc --noEmit
npm run build
```

For OT-path or operational changes, start the local lab and run from the
repository root:

```powershell
./scripts/depotflux.ps1 verify
```

Pull requests should explain the problem and scope, identify security-boundary
changes, add or update tests, and record any residual limitations. Generated
evidence, `.env` files, databases and local secrets must remain untracked.

## Licence status

The repository owner has not yet selected a software or data licence. Public
visibility alone does not grant reuse rights. Do not submit third-party material
unless its licence and provenance are documented and compatible with the licence
chosen for this repository.
