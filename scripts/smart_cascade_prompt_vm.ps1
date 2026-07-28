# Smart cascade prompt on Axion VM (gateway runs on VM localhost:8000, not Windows).
#
# From Windows PowerShell:
#   .\scripts\smart_cascade_prompt_vm.ps1 -Prompt "explain me about vLLM in an advanced way"
#   .\scripts\smart_cascade_prompt_vm.ps1 -Prompt "What is 2+2?" -MaxTokens 128
#
# Requires: gcloud CLI, VM already bootstrapped (scripts/bootstrap-vm.sh or deploy-vm.ps1).

param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,
    [string]$ProjectId = "$($env:GCP_PROJECT)",
    [string]$Zone = "us-central1-a",
    [string]$InstanceName = "neuroswarm-axion",
    [int]$MaxTokens = 128,
    [int]$TimeoutSec = 600
)

$ErrorActionPreference = "Stop"
$gcloudBin = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin"
if (Test-Path $gcloudBin) { $env:Path = "$gcloudBin;$env:Path" }

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Error "gcloud not found. Install Google Cloud SDK or add it to PATH."
}

$localSh = Join-Path $PSScriptRoot "smart_cascade_prompt.sh"
if (-not (Test-Path $localSh)) {
    Write-Error "Missing $localSh"
}

$remoteSh = "/tmp/ns-smart-cascade-$(New-Guid).sh"
$remotePrompt = "/tmp/ns-smart-cascade-prompt-$(New-Guid).txt"
$localPrompt = Join-Path $env:TEMP ("ns-prompt-" + [guid]::NewGuid().ToString("n") + ".txt")
[System.IO.File]::WriteAllText($localPrompt, $Prompt)

Write-Host "Smart cascade on VM $InstanceName ($Zone)" -ForegroundColor Cyan
Write-Host "Prompt: $Prompt"
Write-Host ""

try {
    gcloud compute scp $localSh "${InstanceName}:${remoteSh}" --zone=$Zone --project=$ProjectId | Out-Null
    gcloud compute scp $localPrompt "${InstanceName}:${remotePrompt}" --zone=$Zone --project=$ProjectId | Out-Null

    $remoteCmd = @"
set -euo pipefail
sed -i 's/\r`$//' $remoteSh
chmod +x $remoteSh
bash $remoteSh -f $remotePrompt -m $MaxTokens -t $TimeoutSec
rm -f $remoteSh $remotePrompt
"@

    gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --command $remoteCmd
}
finally {
    Remove-Item -Force $localPrompt -ErrorAction SilentlyContinue
}
