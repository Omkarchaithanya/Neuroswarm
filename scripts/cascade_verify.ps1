# 4-phase cascade verification: direct tiers + gateway routing + quality gradient.
# Usage: .\scripts\cascade_verify.ps1
param(
    [string]$LogPath = "debug-e58bf2.log",
    [string]$SessionId = "e58bf2"
)

$ErrorActionPreference = "Continue"
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
        runId        = "cascade-verify"
    } | ConvertTo-Json -Compress
    #region agent log
    Add-Content -Path $LogPath -Value $entry -Encoding utf8
    #endregion
}

function Invoke-Chat {
    param(
        [string]$Url,
        [string]$Label,
        [string]$Prompt,
        [int]$MaxTokens = 256,
        [string]$HypothesisId = "H0"
    )
    $body = @{
        model      = "default"
        messages   = @(@{ role = "user"; content = $Prompt })
        max_tokens = $MaxTokens
        stream     = $false
    } | ConvertTo-Json -Depth 5 -Compress

    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    Write-Host "Prompt: $Prompt"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-RestMethod $Url -Method Post -ContentType "application/json" -Body $body -TimeoutSec 600
        $sw.Stop()
        $text = $r.choices[0].message.content
        $ct = [int]$r.usage.completion_tokens
        $lat = [math]::Round($sw.Elapsed.TotalSeconds, 3)
        $tps = if ($sw.Elapsed.TotalSeconds -gt 0) { [math]::Round($ct / $sw.Elapsed.TotalSeconds, 3) } else { 0 }
        $tier = $null
        if ($r.PSObject.Properties.Name -contains "tier_used") { $tier = $r.tier_used }
        if ($r.metrics) {
            if ($r.metrics.tier_used) { $tier = $r.metrics.tier_used }
        }
        Write-Host "Latency: ${lat}s | Comp tok: $ct | Tok/s: $tps"
        if ($tier) { Write-Host "Tier used: $tier" }
        $preview = if ($text.Length -gt 200) { $text.Substring(0, 200) + "..." } else { $text }
        Write-Host "Response: $preview" -ForegroundColor Green
        Write-DebugLog $HypothesisId "cascade_verify.ps1" "ok" @{
            label = $Label; latency_s = $lat; completion_tokens = $ct; tok_per_s = $tps; tier_used = $tier
        }
        return [pscustomobject]@{ Label = $Label; Latency = $lat; CompTok = $ct; TokS = $tps; Tier = $tier; Ok = $true }
    }
    catch {
        $sw.Stop()
        Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
        Write-DebugLog $HypothesisId "cascade_verify.ps1" "fail" @{ label = $Label; error = $_.Exception.Message }
        return [pscustomobject]@{ Label = $Label; Latency = $null; CompTok = $null; TokS = $null; Tier = $null; Ok = $false }
    }
}

Write-Host "Neuroswarm 4-phase verify — $(Get-Date -Format o)" -ForegroundColor Green

# Phase B — direct tier probes (quality gradient)
$easy = "What is 2+2? Answer in one word."
$med = "Explain in 2 sentences the difference between TCP and UDP."
$hard = "Solve step by step: A train leaves at 9am at 60 mph. Another leaves 300 miles away at 10am at 80 mph toward it. When do they meet?"

$rows = @(
    (Invoke-Chat "http://127.0.0.1:8081/v1/chat/completions" "B1 Tier1 (0.5B basic)" $easy 32 "H-B1")
    (Invoke-Chat "http://127.0.0.1:8082/v1/chat/completions" "B2 Tier2 (3B medium)" $med 200 "H-B2")
    (Invoke-Chat "http://127.0.0.1:8083/v1/chat/completions" "B3 Tier3 (7B advanced)" $hard 400 "H-B3")
    (Invoke-Chat "http://127.0.0.1:8000/v1/chat/completions" "C1 Gateway easy" $easy 64 "H-C1")
    (Invoke-Chat "http://127.0.0.1:8000/v1/chat/completions" "C2 Gateway medium" $med 200 "H-C2")
    (Invoke-Chat "http://127.0.0.1:8000/v1/chat/completions" "C3 Gateway hard" $hard 400 "H-C3")
)

Write-Host "`n--- Summary ---" -ForegroundColor Yellow
$rows | Format-Table Label, Latency, CompTok, TokS, Tier, Ok -AutoSize

$ok = ($rows | Where-Object { $_.Ok }).Count
Write-DebugLog "H0" "cascade_verify.ps1" "summary" @{ passed = $ok; total = $rows.Count }
if ($ok -lt 6) { exit 1 }
