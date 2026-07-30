# Send one prompt to a tier and print latency, tok/s, and full response.
# Usage:
#   .\scripts\tier_prompt.ps1 -Tier 1 -Prompt "What is 2+2?"
#   .\scripts\tier_prompt.ps1 -Tier 3 -Prompt "Explain quantum entanglement" -MaxTokens 400
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 3)]
    [int]$Tier,
    [string]$Prompt = "What is 2+2? Answer briefly.",
    [int]$MaxTokens = 128,
    [int]$TimeoutSec = 600
)

$ports = @{ 1 = 8081; 2 = 8082; 3 = 8083 }
$models = @{ 1 = "tier1"; 2 = "tier2"; 3 = "tier3" }
$names = @{
    1 = "Qwen2.5-0.5B (fast / basic)"
    2 = "Qwen2.5-3B (medium)"
    3 = "DeepSeek-R1-7B (advanced)"
}

$port = $ports[$Tier]
$bodyHash = @{
    model      = $models[$Tier]
    messages   = @(@{ role = "user"; content = $Prompt })
    max_tokens = $MaxTokens
    stream     = $false
}
# Tier3 (DeepSeek-R1): skip chain-of-thought for direct answers + lower latency
if ($Tier -eq 3) {
    $bodyHash["chat_template_kwargs"] = @{ enable_thinking = $false }
    $bodyHash["messages"] = @(
        @{ role = "system"; content = "Answer directly and concisely. Do not use chain-of-thought." }
        @{ role = "user"; content = $Prompt }
    )
}
$body = $bodyHash | ConvertTo-Json -Depth 6 -Compress

Write-Host "Tier $Tier — $($names[$Tier]) — http://127.0.0.1:$port" -ForegroundColor Cyan
Write-Host "Prompt: $Prompt`n"

$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $r = Invoke-RestMethod "http://127.0.0.1:$port/v1/chat/completions" `
        -Method Post -ContentType "application/json" -Body $body -TimeoutSec $TimeoutSec
    $sw.Stop()
    $text = $r.choices[0].message.content
    if ([string]::IsNullOrWhiteSpace($text) -and $r.choices[0].message.reasoning_content) {
        $text = $r.choices[0].message.reasoning_content
    }
    $text = $text -replace '(?s)^[\s\S]*?(?:|</think>)\s*', ''
    $text = $text.Trim()
    $pt = [int]$r.usage.prompt_tokens
    $ct = [int]$r.usage.completion_tokens
    $lat = [math]::Round($sw.Elapsed.TotalSeconds, 3)
    $tps = if ($sw.Elapsed.TotalSeconds -gt 0) { [math]::Round($ct / $sw.Elapsed.TotalSeconds, 3) } else { 0 }

    Write-Host "--- Metrics ---" -ForegroundColor Yellow
    Write-Host "Latency (wall)     : ${lat}s"
    Write-Host "Prompt tokens      : $pt"
    Write-Host "Completion tokens  : $ct"
    Write-Host "Completion tok/s   : $tps"
    Write-Host "`n--- Response ---" -ForegroundColor Green
    Write-Host $text
}
catch {
    $sw.Stop()
    Write-Host "ERROR after $([math]::Round($sw.Elapsed.TotalSeconds,1))s: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
