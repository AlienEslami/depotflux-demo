$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$demoDirectory = Join-Path $repoRoot '.demo'
$backupDirectory = Join-Path $demoDirectory 'backups'
$environmentFile = Join-Path $demoDirectory 'ot-lab.env'
New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null

$localEnvironment = @{}
if (Test-Path -LiteralPath $environmentFile) {
    Get-Content -LiteralPath $environmentFile | ForEach-Object {
        if ($_ -match '^([^#=]+)=(.*)$') {
            $localEnvironment[$matches[1]] = $matches[2]
        }
    }
}

$requiredSecrets = @(
    'DEMO_CONTROL_API_KEY'
    'DEMO_EMERGENCY_API_KEY'
    'DEMO_GATEWAY_API_KEY'
    'DEMO_DATABASE_PASSWORD'
    'DEMO_OPERATOR_API_KEY'
    'DEMO_APPROVER_API_KEY'
    'DEMO_AUDITOR_API_KEY'
    'DEMO_ADMIN_API_KEY'
)
foreach ($name in $requiredSecrets) {
    if (-not $localEnvironment[$name]) {
        $localEnvironment[$name] = [guid]::NewGuid().ToString('N')
    }
}
$localEnvironment['DEMO_AUTH_MODE'] = 'api_key'

@(
    'DEMO_AUTH_MODE=api_key'
    $requiredSecrets | ForEach-Object { "$_=$($localEnvironment[$_])" }
) | Set-Content -LiteralPath $environmentFile -Encoding ascii

Push-Location $repoRoot
try {
    docker compose --env-file $environmentFile up --build --detach --wait
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up exited with code $LASTEXITCODE"
    }
    docker compose --env-file $environmentFile exec -T api `
        python -m aggregator_demo.admin seed --wait --timeout 120
    if ($LASTEXITCODE -ne 0) {
        throw "DepotFlux seed exited with code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'DepotFlux synthetic OT lab is healthy and seeded.'
Write-Host 'Dashboard: http://127.0.0.1:3000'
Write-Host 'API docs:  http://127.0.0.1:8000/docs'
Write-Host 'Metrics:   http://127.0.0.1:8000/metrics'
Write-Host 'Monitor:   http://127.0.0.1:9100/metrics/security-summary'
Write-Host 'Run ./scripts/depotflux.ps1 credentials to display local role and control keys.'
Write-Host "Local configuration: $environmentFile"
