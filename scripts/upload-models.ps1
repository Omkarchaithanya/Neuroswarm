param(
  [string]$HostAlias = "neuroswarm-axion.us-central1-a.$($env:GCP_PROJECT)",
  [string]$ProjectId = "$($env:GCP_PROJECT)",
  [string]$Zone = "us-central1-a",
  [string]$InstanceName = "neuroswarm-axion",
  [string]$LocalModelDir = (Join-Path (Get-Location).Path "models"),
  [string]$RemoteModelDir = "/models",
  [switch]$PreferGcloud
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

function Invoke-Remote {
  param([Parameter(Mandatory = $true)][string]$Command)
  if ($PreferGcloud -and -not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud was requested with -PreferGcloud but was not found on PATH."
  }
  if ($PreferGcloud -or (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    gcloud compute ssh $InstanceName --zone $Zone --project $ProjectId --command $Command
  } else {
    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
      throw "Neither gcloud nor ssh was found on PATH."
    }
    ssh $HostAlias $Command
  }
}

function Copy-ModelToRemote {
  param([Parameter(Mandatory = $true)][string]$Path)
  if ($PreferGcloud -and -not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud was requested with -PreferGcloud but was not found on PATH."
  }
  if ($PreferGcloud -or (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    gcloud compute scp $Path "${InstanceName}:$RemoteModelDir/" --zone $Zone --project $ProjectId
  } else {
    if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
      throw "Neither gcloud nor scp was found on PATH."
    }
    scp $Path "${HostAlias}:$RemoteModelDir/"
  }
}

if (-not (Test-Path $LocalModelDir)) {
  throw "Local model directory does not exist: $LocalModelDir"
}

$requiredModels = @(
  "qwen2.5-0.5b-instruct-q4_k_m.gguf",
  "Llama-3.2-3B-Instruct-Q5_K_M.gguf",
  "Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf"
)

foreach ($name in $requiredModels) {
  $path = Join-Path $LocalModelDir $name
  if (-not (Test-Path $path)) {
    throw "Missing required model: $path"
  }
}

$quotedRemoteModelDir = "'" + $RemoteModelDir.Replace("'", "'\''") + "'"
Invoke-Checked "Create remote model directory" {
  Invoke-Remote "sudo mkdir -p $quotedRemoteModelDir && sudo chown `$(whoami):`$(id -gn) $quotedRemoteModelDir"
}

foreach ($name in $requiredModels) {
  $path = Join-Path $LocalModelDir $name
  Invoke-Checked "Upload $name" {
    Copy-ModelToRemote -Path $path
  }
}

Invoke-Checked "Create canonical model aliases" {
  Invoke-Remote "cd ~/neuroswarm-arm && MODEL_DIR=$RemoteModelDir bash scripts/prepare-models.sh --source-dir $RemoteModelDir"
}

Write-Host ""
Write-Host "Model upload complete."
Write-Host "Remote model directory: $RemoteModelDir"
