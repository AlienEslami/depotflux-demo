param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'seed', 'verify', 'backup', 'restore', 'reset', 'credentials', 'config')]
    [string]$Command = 'status',
    [string]$BackupPath,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$demoDirectory = Join-Path $repoRoot '.demo'
$backupDirectory = Join-Path $demoDirectory 'backups'
$environmentFile = Join-Path $demoDirectory 'ot-lab.env'

function Require-EnvironmentFile {
    if (-not (Test-Path -LiteralPath $environmentFile)) {
        throw "Local configuration is missing. Run ./scripts/depotflux.ps1 start first."
    }
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    Require-EnvironmentFile
    Push-Location $repoRoot
    try {
        & docker compose --env-file $environmentFile @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

switch ($Command) {
    'start' {
        & (Join-Path $PSScriptRoot 'start_ot_lab.ps1')
    }
    'stop' {
        Invoke-Compose down --remove-orphans
    }
    'status' {
        Invoke-Compose ps
    }
    'seed' {
        Invoke-Compose exec -T api python -m aggregator_demo.admin seed --wait --timeout 120
    }
    'verify' {
        & (Join-Path $PSScriptRoot 'run_ot_evidence.ps1')
    }
    'backup' {
        Require-EnvironmentFile
        New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
        if (-not $BackupPath) {
            $BackupPath = Join-Path $backupDirectory ("depotflux-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        }
        $resolvedParent = (Resolve-Path -LiteralPath (Split-Path -Parent $BackupPath)).Path
        $resolvedBackupRoot = (Resolve-Path -LiteralPath $backupDirectory).Path
        if ($resolvedParent -ne $resolvedBackupRoot) {
            throw "Backups must be written directly under $resolvedBackupRoot"
        }
        $filename = Split-Path -Leaf $BackupPath
        Invoke-Compose exec -T api python -m aggregator_demo.admin backup --output "/backups/$filename"
        Write-Host "Backup created: $BackupPath"
    }
    'restore' {
        Require-EnvironmentFile
        if (-not $Force) {
            throw 'Restore replaces current application data. Re-run with -Force.'
        }
        if (-not $BackupPath) {
            throw 'Restore requires -BackupPath.'
        }
        $resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
        $resolvedBackupRoot = (Resolve-Path -LiteralPath $backupDirectory).Path
        if ((Split-Path -Parent $resolvedBackup) -ne $resolvedBackupRoot) {
            throw "Restore files must be directly under $resolvedBackupRoot"
        }
        $filename = Split-Path -Leaf $resolvedBackup
        Invoke-Compose stop worker
        try {
            Invoke-Compose exec -T api python -m aggregator_demo.admin restore `
                --input "/backups/$filename" --confirm-restore
        } finally {
            Invoke-Compose start worker
        }
    }
    'reset' {
        if (-not $Force) {
            throw 'Reset removes the synthetic database volume. Re-run with -Force.'
        }
        Invoke-Compose down --volumes --remove-orphans
        & (Join-Path $PSScriptRoot 'start_ot_lab.ps1')
    }
    'credentials' {
        Require-EnvironmentFile
        Get-Content -LiteralPath $environmentFile | Where-Object {
            $_ -match '^DEMO_(OPERATOR|APPROVER|AUDITOR|ADMIN|CONTROL|EMERGENCY)_API_KEY='
        }
    }
    'config' {
        Invoke-Compose exec -T api python -m aggregator_demo.admin check-config
    }
}
