[CmdletBinding(PositionalBinding = $false)]
param(
  [string]$ProjectId = "$($env:GCP_PROJECT)",
  [string]$Zone = "us-central1-a",
  [string]$InstanceName = "neuroswarm-axion",
  [string]$RemotePath = "",
  [string]$LocalPath = "",
  [string[]]$Files = @(),
  [switch]$PreferGcloud
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes args as literal strings, so @("a","b") leaks tokens
# into other parameters. Strip array/quote syntax rather than scp'ing garbage.
$Files = @(
  $Files |
    ForEach-Object { $_ -replace '^@\(', '' -replace '\)$', '' } |
    ForEach-Object { $_.Trim().Trim(',').Trim('"').Trim("'") } |
    Where-Object { $_ }
)

if ([string]::IsNullOrWhiteSpace($LocalPath)) {
  $LocalPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$gcloudBin = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin"
if (Test-Path $gcloudBin) { $env:Path = "$gcloudBin;$env:Path" }

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "gcloud not found on PATH."
}

if ($ProjectId -notmatch '^[a-z][a-z0-9-]{5,29}$') {
  if (-not [string]::IsNullOrWhiteSpace($ProjectId)) {
    Write-Warning "Ignoring invalid -ProjectId '$ProjectId'; resolving from gcloud config."
  }
  $ProjectId = (& gcloud config get-value project 2>$null | Out-String).Trim()
}
if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "(unset)") {
  throw "ProjectId required. Run: gcloud config set project YOUR_PROJECT_ID"
}

if ([string]::IsNullOrWhiteSpace($RemotePath)) {
  $remoteHome = (& gcloud compute ssh $InstanceName --zone $Zone --project $ProjectId --command 'printf "%s" "$HOME"' | Out-String).Trim()
  if ([string]::IsNullOrWhiteSpace($remoteHome)) {
    throw "Failed to resolve remote home on $InstanceName (project=$ProjectId, zone=$Zone)."
  }
  $RemotePath = "$remoteHome/neuroswarm-arm"
}

if ($Files.Count -eq 0) {
  $Files = @(
    "docker-compose.yaml",
    "docker-compose.tier3-reasoning.yaml",
    "scripts/patch-tier3-reasoning.sh",
    "scripts/start-tiers-axion.sh",
    "scripts/remote-compose-up.sh",
    "scripts/verify-batching-slots.sh",
    "scripts/ensure-compose-models.sh"
  )
}

$missing = @()
$toCopy = @()
foreach ($rel in $Files) {
  $local = Join-Path $LocalPath ($rel -replace '/', [IO.Path]::DirectorySeparatorChar)
  if (-not (Test-Path $local)) {
    $missing += $rel
    continue
  }
  $toCopy += [PSCustomObject]@{ Rel = $rel; Local = $local }
}

if ($missing.Count -gt 0) {
  Write-Warning "Skipping missing local files:"
  $missing | ForEach-Object { Write-Warning "  $_" }
}

if ($toCopy.Count -eq 0) {
  throw "No files to copy. Pass -Files path1,path2 or fix missing paths."
}

Write-Host "Sync $($toCopy.Count) file(s) -> ${InstanceName}:$RemotePath"

foreach ($item in $toCopy) {
  if ($item.Rel -match '^scripts/') {
    $dest = "${InstanceName}:${RemotePath}/scripts/"
  } else {
    $dest = "${InstanceName}:${RemotePath}/"
  }
  Write-Host "  $($item.Rel)"
  & gcloud compute scp $item.Local $dest --zone $Zone --project $ProjectId
  if ($LASTEXITCODE -ne 0) {
    throw "scp failed for $($item.Rel)"
  }
}

& gcloud compute ssh $InstanceName --zone $Zone --project $ProjectId --command `
  "find '$RemotePath/scripts' -name '*.sh' -print0 2>/dev/null | xargs -0 -r sed -i 's/\r`$//' ; true"

Write-Host "sync-vm-files: done ($($toCopy.Count) file(s))"
