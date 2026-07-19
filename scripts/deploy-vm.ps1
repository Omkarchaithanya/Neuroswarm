param(
  [string]$ProjectId = "$($env:GCP_PROJECT)",
  [string]$Zone = "us-central1-a",
  [string]$InstanceName = "neuroswarm-axion",
  [string]$RemotePath = "",
  [string]$LocalPath = (Get-Location).Path,
  [string]$DemoModelPath = "",
  [switch]$SkipLocalInstall,
  [switch]$SkipBootstrap,
  [switch]$SkipEvidence
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Label,
    [Parameter(Mandatory = $true)]
    [scriptblock]$Command
  )

  Write-Host ""
  Write-Host "== $Label =="
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE."
  }
}

function Invoke-GcloudSsh {
  param([Parameter(Mandatory = $true)][string]$Command)
  & gcloud compute ssh $InstanceName --zone $Zone --project $ProjectId --command $Command
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

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "gcloud not found on PATH. Install Google Cloud CLI or run scripts/sync-vm.ps1 with a working SSH alias."
}

if ([string]::IsNullOrWhiteSpace($RemotePath)) {
  $RemotePath = "$(Get-RemoteHome)/neuroswarm-arm"
}

if (-not $SkipLocalInstall) {
  if (-not (Test-Path ".venv")) {
    Invoke-Checked "Create local virtual environment" { python -m venv .venv }
  }
  Invoke-Checked "Upgrade pip" { & ".\.venv\Scripts\python.exe" -m pip install --upgrade pip }
  Invoke-Checked "Install local package with benchmark dependencies" { & ".\.venv\Scripts\python.exe" -m pip install -e ".[bench]" }
  Invoke-Checked "Compile Python sources" { & ".\.venv\Scripts\python.exe" -m compileall neuroswarm_arm benchmarks }
  Invoke-Checked "Run local benchmark harness" { & ".\.venv\Scripts\python.exe" benchmarks\run_all.py --out work\benchmarks\local-run-all.json }
}

Invoke-Checked "Sync repository to VM" {
  powershell -ExecutionPolicy Bypass -File scripts\sync-vm.ps1 `
    -ProjectId $ProjectId `
    -Zone $Zone `
    -InstanceName $InstanceName `
    -RemotePath $RemotePath `
    -LocalPath $LocalPath `
    -PreferGcloud
}

Invoke-Checked "Validate VM before bootstrap" {
  Invoke-GcloudSsh "cd $RemotePath && bash scripts/validate-vm.sh"
}

if ($DemoModelPath -ne "") {
  Invoke-Checked "Prepare smoke model symlinks" {
    Invoke-GcloudSsh "cd $RemotePath && bash scripts/prepare-models.sh --demo-source '$DemoModelPath'"
  }
}

if (-not $SkipBootstrap) {
  Invoke-Checked "Bootstrap VM runtime" {
    Invoke-GcloudSsh "cd $RemotePath && bash scripts/bootstrap-vm.sh"
  }
}

if (-not $SkipEvidence) {
  Invoke-Checked "Capture deployment evidence" {
    Invoke-GcloudSsh "cd $RemotePath && bash scripts/capture-evidence.sh"
  }

  $localEvidence = Join-Path $LocalPath "benchmarks\results"
  New-Item -ItemType Directory -Force -Path $localEvidence | Out-Null
  Invoke-Checked "Copy evidence back to local workspace" {
    gcloud compute scp --recurse `
      "${InstanceName}:$RemotePath/benchmarks/results/*" `
      $localEvidence `
      --zone $Zone `
      --project $ProjectId
  }
}

Write-Host ""
Write-Host "Deployment workflow complete."
Write-Host "Remote project path: $RemotePath"
Write-Host "Local evidence path: benchmarks\results"
