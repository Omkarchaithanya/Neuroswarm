# Tier latency / tok/s verification — direct llama-server ports 8081-8083
# Usage: .\scripts\tier_verify.ps1
param(
    [string]$LogPath = "debug-e58bf2.log",
    [string]$SessionId = "e58bf2"
)

$ErrorActionPreference = "Continue"

function Write-DebugLog {
    param([string]$HypothesisId, [string]$Location, [string]$Message, [hashtable]$Data)
    $entry = @{
        sessionId    = $SessionId
        hypothesisId = $HypothesisId
        location     = $Location
        message      = $Message
        data         = $Data
        timestamp    = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        runId        = "tier-verify"
    } | ConvertTo-Json -Compress
    Add-Content -Path $LogPath -Value $entry -Encoding utf8
}

function Invoke-TierChat {
    param(
        [int]$Tier,
        [int]$Port,
        [string]$Model,
        [string]$Prompt,
        [int]$MaxTokens = 256
    )
    $body = @{
        model      = $Model
        messages   = @(@{ role = "user"; content = $Prompt })
        max_tokens = $MaxTokens
        stream     = $false
    }
    if ($Tier -eq 3) {
        $body["chat_template_kwargs"] = @{ enable_thinking = $false }
    }
    $body = $body | ConvertTo-Json -Depth 6 -Compress

    Write-Host "`n=== TIER $Tier ($Model) port $Port ===" -ForegroundColor Cyan
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:$Port/v1/chat/completions" `
            -Method Post -ContentType "application/json" -Body $body -TimeoutSec 600
        $sw.Stop()
        $text = $r.choices[0].message.content
        $pt = [int]$r.usage.prompt_tokens
        $ct = [int]$r.usage.completion_tokens
        $lat = [math]::Round($sw.Elapsed.TotalSeconds, 3)
        $tps = if ($sw.Elapsed.TotalSeconds -gt 0) { [math]::Round($ct / $sw.Elapsed.TotalSeconds, 3) } else { 0 }
        Write-Host "Latency  : ${lat}s"
        Write-Host "Tokens   : prompt=$pt completion=$ct"
        Write-Host "Tok/s    : $tps (completion)"
        $preview = if ($text.Length -gt 120) { $text.Substring(0, 120) + "..." } else { $text }
        Write-Host "Response : $preview"
        Write-DebugLog "H$tier" "tier_verify.ps1" "tier_ok" @{
            tier = $Tier; port = $Port; model = $Model
            latency_s = $lat; prompt_tokens = $pt; completion_tokens = $ct; tok_per_s = $tps
            chars = $text.Length
        }
        return [pscustomobject]@{ Tier = $Tier; Model = $Model; Latency = $lat; CompTok = $ct; TokS = $tps; Preview = $preview; Ok = $true }
    }
    catch {
        $sw.Stop()
        Write-Host "FAIL: $_" -ForegroundColor Red
        Write-DebugLog "H$tier" "tier_verify.ps1" "tier_fail" @{ tier = $Tier; port = $Port; error = $_.Exception.Message }
        return [pscustomobject]@{ Tier = $Tier; Model = $Model; Latency = $null; CompTok = $null; TokS = $null; Preview = $_.Exception.Message; Ok = $false }
    }
}

$promptEasy = "What is 2+2? Answer in one word."
$promptMed = "Explain in 2 sentences the difference between TCP and UDP."
$promptHard = "Solve step by step: A train leaves Station A at 9am at 60 mph. Another leaves Station B 300 miles away at 10am at 80 mph toward A. When do they meet?"

Write-Host "Neuroswarm tier verify — $(Get-Date -Format o)" -ForegroundColor Green

$rows = @(
    (Invoke-TierChat -Tier 1 -Port 8081 -Model "tier1" -Prompt $promptEasy -MaxTokens 32)
    (Invoke-TierChat -Tier 2 -Port 8082 -Model "tier2" -Prompt $promptMed -MaxTokens 200)
    (Invoke-TierChat -Tier 3 -Port 8083 -Model "tier3" -Prompt $promptHard -MaxTokens 400)
)

Write-Host "`n--- Summary ---" -ForegroundColor Yellow
$rows | Format-Table Tier, Model, Latency, CompTok, TokS, Ok -AutoSize

$ok = ($rows | Where-Object { $_.Ok }).Count
Write-DebugLog "H0" "tier_verify.ps1" "summary" @{ passed = $ok; total = $rows.Count }
if ($ok -lt 3) { exit 1 }
