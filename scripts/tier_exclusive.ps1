# Run a prompt against one tier with others stopped (low-RAM hosts <16GB).
# Cascade routes one tier per request — exclusive mode matches that and cuts latency.
# Usage: .\scripts\tier_exclusive.ps1 -Tier 3 -Prompt "Your question" -MaxTokens 120
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 3)]
    [int]$Tier,
    [string]$Prompt = "What is 2+2? One word.",
    [int]$MaxTokens = 64,
    [int]$TimeoutSec = 300,
    [switch]$RestoreAll
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$all = @("tier1", "tier2", "tier3")
$target = "tier$Tier"
$stop = $all | Where-Object { $_ -ne $target }

Write-Host "Stopping $($stop -join ', ') to free CPU/RAM for $target..." -ForegroundColor Yellow
docker compose -f docker-compose.yaml -f docker-compose.local.yaml stop @stop | Out-Null
Start-Sleep -Seconds 8

& "$PSScriptRoot\tier_prompt.ps1" -Tier $Tier -Prompt $Prompt -MaxTokens $MaxTokens -TimeoutSec $TimeoutSec
$code = $LASTEXITCODE

if ($RestoreAll) {
    Write-Host "Restoring all tiers..." -ForegroundColor Yellow
    docker compose -f docker-compose.yaml -f docker-compose.local.yaml up -d tier1 tier2 tier3 | Out-Null
}

exit $code
