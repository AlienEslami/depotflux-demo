$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$evidenceDirectory = Join-Path $repoRoot '.demo\evidence'
New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null

Push-Location $repoRoot
try {
    python -m pytest tests/test_modbus_tcp_gateway.py tests/test_ot_dispatch_api.py --junitxml (Join-Path $evidenceDirectory 'ot-scenarios.junit.xml')
    python scripts/compose_smoke.py --output (Join-Path $evidenceDirectory 'compose-smoke.json')
    python scripts/verify_network_isolation.py --output (Join-Path $evidenceDirectory 'network-isolation.json')
    docker compose --env-file .demo/ot-lab.env ps --format json | Set-Content -LiteralPath (Join-Path $evidenceDirectory 'container-health.jsonl') -Encoding utf8
} finally {
    Pop-Location
}

Write-Host "Evidence written to $evidenceDirectory"
