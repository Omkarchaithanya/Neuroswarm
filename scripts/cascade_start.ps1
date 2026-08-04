# Start Neuroswarm cascade stack (Windows x86 local).
# Usage: .\scripts\cascade_start.ps1
param(
    [string]$LogPath = "debug-e58bf2.log",
    [string]$SessionId = "e58bf2",
    [int]$WaitMinutes = 25
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Write-DebugLog {
    param([string]$HypothesisId, [string]$Location, [string]$Message, [hashtable]$Data)
    $entry = @{
        sessionId    = $SessionId
        hypothesisId = $HypothesisId
        location     = $Location
        message      = $Message
        data         = $Data
        timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        runId        = "cascade-start"
    } | ConvertTo-Json -Compress
    #region agent log
    Add-Content -Path $LogPath -Value $entry -Encoding utf8
    #endregion
}

$required = @(
    "xLAM-2-1b-fc-r-Q4_0.gguf",
    "xLAM-2-3b-fc-r-Q4_0.gguf",
    "DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
)

Write-Host "=== Neuroswarm cascade start ===" -ForegroundColor Green

try { docker info *> $null } catch {
    Write-Host "ERROR: Docker daemon is not running. Start Docker Desktop first." -ForegroundColor Red
    Write-DebugLog "H1" "cascade_start.ps1" "docker_down" @{}
    exit 1
}

$memBytes = [int64](docker info --format "{{.MemTotal}}" 2>$null)
$memGiB = [math]::Round($memBytes / 1GB, 1)
Write-Host "Docker memory: ${memGiB} GiB"
Write-DebugLog "H4" "cascade_start.ps1" "docker_memory" @{ mem_gib = $memGiB }
if ($memGiB -lt 12) {
    Write-Host "WARNING: Docker has < 12 GiB RAM. Tier3 (7B) may fail to load." -ForegroundColor Yellow
    Write-Host "  Fix: Docker Desktop -> Settings -> Resources -> Memory -> 16 GiB" -ForegroundColor Yellow
}

$missing = @()
foreach ($f in $required) {
    if (-not (Test-Path "models\$f")) { $missing += $f }
}
if ($missing.Count -gt 0) {
    Write-Host "ERROR: Missing models in .\models\:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  $_" }
    Write-DebugLog "H2" "cascade_start.ps1" "models_missing" @{ files = $missing }
    exit 1
}
Write-DebugLog "H2" "cascade_start.ps1" "models_ok" @{ count = $required.Count }

Write-Host "Building gateway (if needed) and starting tier1 tier2 tier3 gateway..."
docker compose -f docker-compose.yaml -f docker-compose.local.yaml up -d --build tier1 tier2 tier3 gateway
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$deadline = (Get-Date).AddMinutes($WaitMinutes)
$services = @("tier1", "tier2", "tier3", "gateway")
while ((Get-Date) -lt $deadline) {
    $status = @{}
    foreach ($s in $services) {
        $c = "neuroswarm-arm-gcp-axion-$s-1"
        $h = docker inspect $c --format "{{.State.Health.Status}}" 2>$null
        if (-not $h) { $h = docker inspect $c --format "{{.State.Status}}" 2>$null }
        $status[$s] = $h
    }
    $line = ($services | ForEach-Object { "$_=$($status[$_])" }) -join " | "
    Write-Host "$(Get-Date -Format HH:mm:ss) $line"
    if (($status.Values | Where-Object { $_ -ne "healthy" }).Count -eq 0) {
        Write-Host "All services healthy." -ForegroundColor Green
        Write-DebugLog "H3" "cascade_start.ps1" "all_healthy" $status
        docker compose -f docker-compose.yaml -f docker-compose.local.yaml ps
        exit 0
    }
    Start-Sleep -Seconds 20
}

Write-Host "TIMEOUT: not all services healthy after ${WaitMinutes}m" -ForegroundColor Red
docker compose -f docker-compose.yaml -f docker-compose.local.yaml ps
Write-DebugLog "H3" "cascade_start.ps1" "health_timeout" @{}
exit 1
