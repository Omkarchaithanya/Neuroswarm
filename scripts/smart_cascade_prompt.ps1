# Smart cascade: auto hardness classify -> start tier -> escalate on low confidence.
# Usage:
#   .\scripts\smart_cascade_prompt.ps1 -Prompt "What is 2+2?"
#   .\scripts\smart_cascade_prompt.ps1 -Prompt "Solve step by step..." -MaxTokens 400
param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,
    [string]$GatewayUrl = "http://127.0.0.1:8000/v1/chat/completions",
    [int]$MaxTokens = 128,
    [int]$TimeoutSec = 600
)

$DebugLogPath = Join-Path (Split-Path $PSScriptRoot -Parent) "debug-bfa34a.log"

function Write-DebugLog {
    param([string]$HypothesisId, [string]$Location, [string]$Message, [hashtable]$Data)
    #region agent log
    $entry = @{
        sessionId    = "bfa34a"
        hypothesisId = $HypothesisId
        location     = $Location
        message      = $Message
        data         = $Data
        timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        runId        = "smart-cascade-prompt"
    } | ConvertTo-Json -Compress
    Add-Content -Path $DebugLogPath -Value $entry -Encoding utf8
    #endregion
}

$body = @{
    model      = "cascade"
    messages   = @(@{ role = "user"; content = $Prompt })
    max_tokens = $MaxTokens
    stream     = $false
} | ConvertTo-Json -Depth 5 -Compress

Write-Host "Smart cascade - $GatewayUrl" -ForegroundColor Cyan
Write-Host "Prompt: $Prompt"
Write-Host ""

Write-DebugLog -HypothesisId "H1" -Location "smart_cascade_prompt.ps1:start" -Message "script_start" -Data @{
    prompt_len = $Prompt.Length
    max_tokens = $MaxTokens
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $r = Invoke-RestMethod $GatewayUrl -Method Post -ContentType "application/json" -Body $body -TimeoutSec $TimeoutSec
    $sw.Stop()
    $text = $r.choices[0].message.content
    if ([string]::IsNullOrWhiteSpace($text) -and $r.choices[0].message.reasoning_content) {
        $text = $r.choices[0].message.reasoning_content
    }
    $thinkTag = "</think>"
    $text = $text -replace "(?s)^[\s\S]*?(?:$thinkTag)\s*", ""
    $text = $text.Trim()
    $pt = [int]$r.usage.prompt_tokens
    $ct = [int]$r.usage.completion_tokens
    $lat = [math]::Round($sw.Elapsed.TotalSeconds, 3)
    $tps = if ($sw.Elapsed.TotalSeconds -gt 0) { [math]::Round($ct / $sw.Elapsed.TotalSeconds, 3) } else { 0 }

    $tierUsed = $null
    $startTier = $null
    $hardnessBand = $null
    $hardnessComplexity = $null

    if ($r.PSObject.Properties.Name -contains "tier_used") { $tierUsed = $r.tier_used }
    if ($r.metrics) {
        if ($r.metrics.tier_used) { $tierUsed = [int]$r.metrics.tier_used }
        if ($r.metrics.cascade_start_tier) { $startTier = [int]$r.metrics.cascade_start_tier }
        if ($r.metrics.hardness_band) { $hardnessBand = [string]$r.metrics.hardness_band }
        if ($r.metrics.hardness_complexity) { $hardnessComplexity = $r.metrics.hardness_complexity }
    }

    Write-DebugLog -HypothesisId "H2" -Location "smart_cascade_prompt.ps1:success" -Message "gateway_ok" -Data @{
        latency_s           = $lat
        tier_used           = $tierUsed
        cascade_start_tier  = $startTier
        hardness_band       = $hardnessBand
        hardness_complexity = $hardnessComplexity
        completion_tokens   = $ct
    }

    Write-Host "--- Routing ---" -ForegroundColor Yellow
    if ($hardnessBand) { Write-Host "Hardness band       : $hardnessBand" }
    if ($startTier) { Write-Host "Cascade start tier  : $startTier" }
    if ($tierUsed) { Write-Host "Tier used (final)   : $tierUsed" }
    if ($hardnessComplexity) { Write-Host "Hardness complexity : $hardnessComplexity" }

    Write-Host ""
    Write-Host "--- Metrics ---" -ForegroundColor Yellow
    Write-Host "Latency (wall)     : ${lat}s"
    Write-Host "Prompt tokens      : $pt"
    Write-Host "Completion tokens  : $ct"
    Write-Host "Completion tok/s   : $tps"
    Write-Host ""
    Write-Host "--- Response ---" -ForegroundColor Green
    Write-Host $text
}
catch {
    $sw.Stop()
    $errMsg = $_.Exception.Message
    Write-DebugLog -HypothesisId "H3" -Location "smart_cascade_prompt.ps1:error" -Message "gateway_fail" -Data @{
        latency_s = [math]::Round($sw.Elapsed.TotalSeconds, 1)
        error     = $errMsg
    }
    Write-Host ("ERROR after {0}s: {1}" -f [math]::Round($sw.Elapsed.TotalSeconds, 1), $errMsg) -ForegroundColor Red
    exit 1
}
