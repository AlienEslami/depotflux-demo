$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$demoDirectory = Join-Path $repoRoot '.demo'
$environmentFile = Join-Path $demoDirectory 'ot-lab.env'
New-Item -ItemType Directory -Force -Path $demoDirectory | Out-Null

if (Test-Path -LiteralPath $environmentFile) {
    $localEnvironment = @{}
    Get-Content -LiteralPath $environmentFile | ForEach-Object {
        if ($_ -match '^([^#=]+)=(.*)$') {
            $localEnvironment[$matches[1]] = $matches[2]
        }
    }
    $controlKey = $localEnvironment['DEMO_CONTROL_API_KEY']
    $emergencyKey = $localEnvironment['DEMO_EMERGENCY_API_KEY']
    $gatewayKey = $localEnvironment['DEMO_GATEWAY_API_KEY']
    $databasePassword = $localEnvironment['DEMO_DATABASE_PASSWORD']
    if (-not $controlKey -or -not $emergencyKey -or -not $gatewayKey -or -not $databasePassword) {
        throw "$environmentFile is incomplete; restore all four required local values or remove the file to regenerate it."
    }
} else {
    $controlKey = [guid]::NewGuid().ToString('N')
    $emergencyKey = [guid]::NewGuid().ToString('N')
    $gatewayKey = [guid]::NewGuid().ToString('N')
    $databasePassword = [guid]::NewGuid().ToString('N')
    @(
        "DEMO_CONTROL_API_KEY=$controlKey"
        "DEMO_EMERGENCY_API_KEY=$emergencyKey"
        "DEMO_GATEWAY_API_KEY=$gatewayKey"
        "DEMO_DATABASE_PASSWORD=$databasePassword"
    ) | Set-Content -LiteralPath $environmentFile -Encoding ascii
}

Push-Location $repoRoot
try {
    docker compose --env-file $environmentFile up --build --detach --wait
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'DepotFlux synthetic OT lab is healthy.'
Write-Host 'Dashboard: http://127.0.0.1:3000'
Write-Host 'API docs:  http://127.0.0.1:8000/docs'
Write-Host 'Monitor:   http://127.0.0.1:9100/metrics/security-summary'
Write-Host "Dashboard control key: $controlKey"
Write-Host "Emergency drill key:   $emergencyKey"
Write-Host 'These credentials are local, ephemeral, and stored in .demo/ot-lab.env.'
