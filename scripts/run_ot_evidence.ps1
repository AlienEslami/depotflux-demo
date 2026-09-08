$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$evidenceDirectory = Join-Path $repoRoot '.demo\evidence'
New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null

Push-Location $repoRoot
try {
    python -m pytest tests/test_modbus_tcp_gateway.py tests/test_ot_dispatch_api.py --junitxml (Join-Path $evidenceDirectory 'ot-scenarios.junit.xml')
    if ($LASTEXITCODE -ne 0) { throw "OT scenario tests exited with code $LASTEXITCODE" }
    python scripts/compose_smoke.py --output (Join-Path $evidenceDirectory 'compose-smoke.json')
    if ($LASTEXITCODE -ne 0) { throw "Compose smoke test exited with code $LASTEXITCODE" }
    python scripts/verify_network_isolation.py --output (Join-Path $evidenceDirectory 'network-isolation.json')
    if ($LASTEXITCODE -ne 0) { throw "Network isolation check exited with code $LASTEXITCODE" }
    python scripts/benchmark_api.py --output (Join-Path $evidenceDirectory 'api-benchmark.json')
    if ($LASTEXITCODE -ne 0) { throw "API benchmark exited with code $LASTEXITCODE" }
    ./scripts/verify_restart_recovery.ps1 -Output (Join-Path $evidenceDirectory 'restart-recovery.json')
    docker compose --env-file .demo/ot-lab.env ps --format json | Set-Content -LiteralPath (Join-Path $evidenceDirectory 'container-health.jsonl') -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "Container health capture exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "Evidence written to $evidenceDirectory"
