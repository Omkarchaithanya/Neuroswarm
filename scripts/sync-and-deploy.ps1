param(
  [ValidateSet("compose", "k8s")]
  [string]$Mode = "compose",
  [string]$ProjectId = "project-5bcdea88-8805-4908-991",
  [string]$Zone = "us-central1-a",
  [string]$InstanceName = "neuroswarm-axion",
  [string]$RemotePath = "",
  [string]$LocalPath = "",
  [switch]$SkipSync,
  [switch]$SkipBuild,
  [switch]$Performix,
  [switch]$Smoke,
  # Default ON: fail deploy when remote health probe fails. Pass -RequireHealth:$false to soft-fail.
  [bool]$RequireHealth = $true
)

$ErrorActionPreference = "Stop"

# Ensure gcloud SDK is on PATH (common Windows install location).
$gcloudBin = "C:\Users\omkar\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
if (Test-Path $gcloudBin) {
  $env:Path = "$gcloudBin;" + $env:Path
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "gcloud not found on PATH. Install Google Cloud CLI."
}

if ([string]::IsNullOrWhiteSpace($LocalPath)) {
  $LocalPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-RemoteHome {
  $remoteHome = & gcloud compute ssh $InstanceName --zone $Zone --project $ProjectId --command 'printf "%s" "$HOME"'
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to resolve remote home directory."
  }
  $remoteHome = ($remoteHome | Out-String).Trim()
  if ([string]::IsNullOrWhiteSpace($remoteHome)) {
    throw "Remote home directory was empty."
  }
  return $remoteHome
}

if ([string]::IsNullOrWhiteSpace($RemotePath)) {
  $RemotePath = "$(Get-RemoteHome)/neuroswarm-arm"
}

function Invoke-GcloudSsh {
  param([Parameter(Mandatory = $true)][string]$Command)
  & gcloud compute ssh $InstanceName --zone $Zone --project $ProjectId --command $Command
  if ($LASTEXITCODE -ne 0) {
    throw "Remote command failed (exit $LASTEXITCODE): $Command"
  }
}

Write-Host "== sync-and-deploy Mode=$Mode Instance=$InstanceName RequireHealth=$RequireHealth =="

if (-not $SkipSync) {
  Write-Host "== Sync repository =="
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "sync-vm.ps1") `
    -ProjectId $ProjectId `
    -Zone $Zone `
    -InstanceName $InstanceName `
    -RemotePath $RemotePath `
    -LocalPath $LocalPath `
    -PreferGcloud
  if ($LASTEXITCODE -ne 0) {
    throw "sync-vm.ps1 failed."
  }
}

# Ensure LF on newly synced scripts.
Invoke-GcloudSsh "find '$RemotePath/scripts' -name '*.sh' -print0 2>/dev/null | xargs -0 -r sed -i 's/\r`$//' ; true"

$envExports = @()
if ($SkipBuild) { $envExports += "SKIP_BUILD=1" }
if ($RequireHealth) { $envExports += "REQUIRE_HEALTH=1" } else { $envExports += "REQUIRE_HEALTH=0" }
if ($Performix) { $envExports += "PERFORMIX=1" }
$envPrefix = if ($envExports.Count -gt 0) { ($envExports -join " ") + " " } else { "" }

if ($Mode -eq "compose") {
  Write-Host "== Remote Compose up =="
  Invoke-GcloudSsh "cd '$RemotePath' && ${envPrefix}bash scripts/remote-compose-up.sh"
  Write-Host "Compose deploy complete. Probe: curl http://<axion-ip>/health"
}
elseif ($Mode -eq "k8s") {
  Write-Host "== Remote k3s + Helm up =="
  Invoke-GcloudSsh "cd '$RemotePath' && bash scripts/install-k3s-axion.sh"
  Invoke-GcloudSsh "cd '$RemotePath' && ${envPrefix}bash scripts/remote-helm-up.sh"
  Write-Host "k8s deploy complete. Probe: curl http://<axion-ip>:30080/health"
}

if ($Smoke) {
  Write-Host "== Smoke probes =="
  $baseHint = if ($Mode -eq "k8s") { "http://127.0.0.1:30080" } else { "http://127.0.0.1" }
  $smokeCmd = @"
set -euo pipefail
BASE='$baseHint'
# Prefer nginx :80 for compose; fall back to gateway / NodePort.
for u in "`$BASE" "http://127.0.0.1:8000" "http://127.0.0.1:30080"; do
  if curl -fsS "`$u/health" >/dev/null 2>&1; then BASE="`$u"; break; fi
done
echo "SMOKE_BASE=`$BASE"
curl -fsS "`$BASE/health" | head -c 500; echo
curl -fsS "`$BASE/ready" >/dev/null
curl -fsS -X POST "`$BASE/workflows" -H 'Content-Type: application/json' -d '{"steps":["smoke"],"name":"deploy_smoke"}' | head -c 300; echo
MEM=`$(curl -fsS "`$BASE/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); print((d.get("memory") or {}).get("provider",""))' 2>/dev/null || true)
echo "memory_provider=`$MEM"
"@
  $smokeCmd = $smokeCmd -replace "`r`n", "`n"
  Invoke-GcloudSsh $smokeCmd
}

Write-Host "sync-and-deploy: success"
