param(
  [string]$HostAlias = "neuroswarm-axion.us-central1-a.$($env:GCP_PROJECT)",
  [string]$ProjectId = "$($env:GCP_PROJECT)",
  [string]$Zone = "us-central1-a",
  [string]$InstanceName = "neuroswarm-axion",
  [string]$RemotePath = "",
  [string]$LocalPath = (Get-Location).Path,
  [switch]$PreferGcloud
)

$ErrorActionPreference = "Stop"

function Get-RemoteHome {
  if ($PreferGcloud -and -not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud was requested with -PreferGcloud but was not found on PATH."
  }

  if (Get-Command gcloud -ErrorAction SilentlyContinue) {
    $remoteHome = & gcloud compute ssh $InstanceName --zone $Zone --project $ProjectId --command 'printf "%s" "$HOME"'
  } else {
    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
      throw "Neither gcloud nor ssh was found on PATH."
    }
    $remoteHome = & ssh $HostAlias 'printf "%s" "$HOME"'
  }
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to resolve remote home directory."
  }

  $remoteHome = ($remoteHome | Out-String).Trim()
  if ([string]::IsNullOrWhiteSpace($remoteHome)) {
    throw "Remote home directory was empty."
  }

  return $remoteHome
}

function Invoke-Remote {
  param([Parameter(Mandatory = $true)][string]$Command)
  if ($PreferGcloud -and -not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud was requested with -PreferGcloud but was not found on PATH."
  }
  if ($PreferGcloud -or (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    & gcloud compute ssh $InstanceName --zone $Zone --project $ProjectId --command $Command
  } else {
    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
      throw "ssh not found on PATH."
    }
    ssh $HostAlias $Command
  }
  if ($LASTEXITCODE -ne 0) {
    throw "Remote command failed: $Command"
  }
}

$remoteHome = Get-RemoteHome
if ([string]::IsNullOrWhiteSpace($RemotePath)) {
  $RemotePath = "$remoteHome/neuroswarm-arm"
}

function Copy-ToRemote {
  param([Parameter(Mandatory = $true)][string]$Staging)
  if ($PreferGcloud -and -not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud was requested with -PreferGcloud but was not found on PATH."
  }
  if ($PreferGcloud -or (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "Copying repository to ${InstanceName}:$RemotePath with gcloud compute scp"
    & gcloud compute scp --recurse "$Staging\*" "${InstanceName}:$RemotePath/" --zone $Zone --project $ProjectId
  } else {
    if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
      throw "scp not found on PATH."
    }
    Write-Host "Copying repository to ${HostAlias}:$RemotePath with scp"
    scp -r "$Staging\*" "${HostAlias}:$RemotePath/"
  }
  if ($LASTEXITCODE -ne 0) {
    throw "Remote copy failed."
  }
}

Write-Host "Creating remote project directory $RemotePath"
Invoke-Remote "mkdir -p $RemotePath"

$temp = Join-Path $env:TEMP ("neuroswarm-sync-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temp | Out-Null

try {
  $staging = Join-Path $temp "neuroswarm-arm"
  robocopy $LocalPath $staging /MIR /XD .git .venv __pycache__ work .pytest_cache /XF *.pyc *.log *.gguf | Out-Null
  if ($LASTEXITCODE -gt 7) {
    throw "robocopy failed with code $LASTEXITCODE."
  }

  Copy-ToRemote -Staging $staging

  # Windows robocopy keeps CRLF; bash scripts need LF on the VM.
  Invoke-Remote "find '$RemotePath/scripts' -name '*.sh' -print0 2>/dev/null | xargs -0 -r sed -i 's/\r`$//' ; true"
} finally {
  Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

Write-Host "Sync complete."
