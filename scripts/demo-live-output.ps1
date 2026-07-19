# Live demo against Neuroswarm on Axion (API is on the VM, not Windows localhost).
#
# From C:\Users\omkar\Neuroswarm in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\demo-live-output.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\demo-live-output.ps1 -Chat
#   powershell -ExecutionPolicy Bypass -File scripts\demo-live-output.ps1 -Chat -Message "Say hello in one sentence."
#   powershell -ExecutionPolicy Bypass -File scripts\demo-live-output.ps1 -Ascr
#   powershell -ExecutionPolicy Bypass -File scripts\demo-live-output.ps1 -Ascr -N 5
#
# Avoid on Windows:
#   bash scripts/demo-live-output.sh          # runs in WSL without Docker
#   cd ~/neuroswarm-arm                       # VM-only path
#   python scripts/ascr-logits-smoke.py --base http://127.0.0.1:8000
#     (localhost on Windows is empty; also use --n 5 not --n 5.)
#   gcloud ... --command "curl ... -d '{...}'" # PowerShell mangles JSON quotes

param(
  [string]$ProjectId = "$($env:GCP_PROJECT)",
  [string]$Zone = "us-central1-a",
  [string]$InstanceName = "neuroswarm-axion",
  [switch]$Chat,
  [switch]$Ascr,
  [int]$N = 5,
  [string]$Message = "Say hello in one sentence."
)

$ErrorActionPreference = "Stop"
$gcloudBin = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin"
if (Test-Path $gcloudBin) { $env:Path = "$gcloudBin;$env:Path" }

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  Write-Error "gcloud not found. Install Google Cloud SDK or add it to PATH."
}

function Invoke-RemoteFile([string]$LocalPath, [string]$RemoteCmd) {
  $remotePath = "/tmp/ns-" + [guid]::NewGuid().ToString("n")
  gcloud compute scp $LocalPath "${InstanceName}:${remotePath}" --zone=$Zone --project=$ProjectId | Out-Null
  gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --command "sed -i 's/\r`$//' $remotePath; $RemoteCmd $remotePath; rm -f $remotePath"
}

if ($Ascr) {
  $remote = @"
#!/usr/bin/env bash
set -euo pipefail
cd ~/neuroswarm-arm
sed -i 's/\r`$//' scripts/ascr-logits-smoke.py 2>/dev/null || true
python3 scripts/ascr-logits-smoke.py --base http://127.0.0.1:8000 --n $N
"@
  $tmp = Join-Path $env:TEMP ("ns-ascr-" + [guid]::NewGuid().ToString("n") + ".sh")
  [System.IO.File]::WriteAllText($tmp, ($remote -replace "`r`n", "`n" -replace "`r", "`n"))
  Write-Host "==> ASCR smoke on $InstanceName (n=$N)"
  Invoke-RemoteFile $tmp "bash"
  Remove-Item -Force $tmp -ErrorAction SilentlyContinue
  exit 0
}

if ($Chat) {
  $payloadObj = @{
    messages   = @(@{ role = "user"; content = $Message })
    max_tokens = 64
  }
  $json = $payloadObj | ConvertTo-Json -Compress -Depth 5
  $tmpJson = Join-Path $env:TEMP ("ns-chat-" + [guid]::NewGuid().ToString("n") + ".json")
  [System.IO.File]::WriteAllText($tmpJson, $json)

  $runner = @'
#!/usr/bin/env bash
set -euo pipefail
PAYLOAD_FILE="$1"
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  --data-binary @"$PAYLOAD_FILE" | python3 -m json.tool
'@
  $tmpSh = Join-Path $env:TEMP ("ns-chat-" + [guid]::NewGuid().ToString("n") + ".sh")
  [System.IO.File]::WriteAllText($tmpSh, ($runner -replace "`r`n", "`n" -replace "`r", "`n"))

  Write-Host "==> Chat on $InstanceName :8000"
  Write-Host "Message: $Message"

  $remoteJson = "/tmp/ns-chat-payload.json"
  $remoteSh = "/tmp/ns-chat-run.sh"
  gcloud compute scp $tmpJson "${InstanceName}:${remoteJson}" --zone=$Zone --project=$ProjectId | Out-Null
  gcloud compute scp $tmpSh "${InstanceName}:${remoteSh}" --zone=$Zone --project=$ProjectId | Out-Null
  gcloud compute ssh $InstanceName --zone=$Zone --project=$ProjectId --command "sed -i 's/\r`$//' $remoteSh; bash $remoteSh $remoteJson; rm -f $remoteSh $remoteJson"
  Remove-Item -Force $tmpJson, $tmpSh -ErrorAction SilentlyContinue
  exit 0
}

Write-Host "==> Full demo on $InstanceName (not Windows / not WSL docker)"
$remote = @'
#!/usr/bin/env bash
set -euo pipefail
cd ~/neuroswarm-arm
sed -i "s/\r$//" scripts/demo-live-output.sh 2>/dev/null || true
bash scripts/demo-live-output.sh
'@
$tmp = Join-Path $env:TEMP ("ns-demo-" + [guid]::NewGuid().ToString("n") + ".sh")
[System.IO.File]::WriteAllText($tmp, ($remote -replace "`r`n", "`n" -replace "`r", "`n"))
Invoke-RemoteFile $tmp "bash"
Remove-Item -Force $tmp -ErrorAction SilentlyContinue
