$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$evidenceDirectory = Join-Path $repoRoot 'evidence\verification'
New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null

Push-Location $repoRoot
try {
    python -m coverage erase
    python -m coverage run -m pytest -q --junitxml=evidence/verification/test-results.xml
    if ($LASTEXITCODE -ne 0) { throw "Python tests failed with code $LASTEXITCODE" }
    python -m coverage json -o evidence/verification/coverage.json
    if ($LASTEXITCODE -ne 0) { throw "Coverage JSON failed with code $LASTEXITCODE" }
    python -m coverage xml -o evidence/verification/coverage.xml
    if ($LASTEXITCODE -ne 0) { throw "Coverage XML failed with code $LASTEXITCODE" }
    python scripts/export_openapi.py --check
    if ($LASTEXITCODE -ne 0) { throw "OpenAPI check failed with code $LASTEXITCODE" }
    Push-Location dashboard
    try {
        npm run lint
        if ($LASTEXITCODE -ne 0) { throw "Dashboard lint failed with code $LASTEXITCODE" }
        npx tsc --noEmit
        if ($LASTEXITCODE -ne 0) { throw "Dashboard type check failed with code $LASTEXITCODE" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Dashboard build failed with code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
