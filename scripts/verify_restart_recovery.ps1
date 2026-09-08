param(
    [string]$EnvironmentFile = '.demo/ot-lab.env',
    [string]$Output = '.demo/evidence/restart-recovery.json'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = if ([System.IO.Path]::IsPathRooted($EnvironmentFile)) {
    [System.IO.Path]::GetFullPath($EnvironmentFile)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $EnvironmentFile))
}
$outputPath = if ([System.IO.Path]::IsPathRooted($Output)) {
    [System.IO.Path]::GetFullPath($Output)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Output))
}
$localEnvironment = @{}
Get-Content -LiteralPath $environmentPath | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        $localEnvironment[$matches[1]] = $matches[2]
    }
}
$headers = @{ Authorization = "Bearer $($localEnvironment['DEMO_AUDITOR_API_KEY'])" }
$baseUrl = 'http://127.0.0.1:8000'
$before = Invoke-RestMethod -Uri "$baseUrl/api/v1/runs?limit=1&offset=0" -Headers $headers
if (-not $before.items.Count) {
    throw 'No persisted run is available for the restart-recovery check.'
}
$runId = $before.items[0].id

Push-Location $repoRoot
try {
    & docker compose --env-file $environmentPath restart api worker
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose restart exited with code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "$baseUrl/health/ready" -TimeoutSec 2
        if ($health.status -eq 'ok') {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $ready) {
    throw 'API did not become ready after restart.'
}

$reloaded = Invoke-RestMethod -Uri "$baseUrl/api/v1/runs/$runId" -Headers $headers
$persisted = $reloaded.id -eq $runId
if (-not $persisted) {
    throw 'Persisted run was not available after service restart.'
}

$evidence = [ordered]@{
    schema_version = 'depotflux-restart-recovery-v1'
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    services_restarted = @('api', 'worker')
    readiness_recovered = $ready
    persisted_run_id = $runId
    persisted_run_reloaded = $persisted
    passed = $ready -and $persisted
}
$parent = Split-Path -Parent $outputPath
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$evidence | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $outputPath -Encoding utf8
$evidence | ConvertTo-Json -Depth 5
