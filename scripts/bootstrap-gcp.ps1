param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,

  [string]$Zone = "us-central1-a",
  [string]$InstanceName = "neuroswarm-axion",
  [string]$MachineType = "c4a-standard-8",
  [string]$FirewallRuleName = "neuroswarm-demo",
  [Parameter(Mandatory = $true)]
  [string]$SourceRanges
)

$ErrorActionPreference = "Stop"

function Invoke-Gcloud {
  param([Parameter(Mandatory = $true)][string[]]$Args)
  & gcloud @Args
  if ($LASTEXITCODE -ne 0) {
    throw "gcloud command failed: gcloud $($Args -join ' ')"
  }
}

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  throw "ProjectId is required."
}

if ($ProjectId -match "\s") {
  throw "ProjectId must be exact project ID and cannot contain spaces. Use gcloud projects list to copy PROJECT_ID."
}

if ($SourceRanges -eq "0.0.0.0/0") {
  throw "Refusing to create public demo firewall. Pass your current public IP as CIDR, for example -SourceRanges 203.0.113.10/32."
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "gcloud not found on PATH."
}

Write-Host "Setting active project to $ProjectId"
Invoke-Gcloud -Args @("config", "set", "project", $ProjectId)

Write-Host "Enabling required APIs"
Invoke-Gcloud -Args @("services", "enable", "compute.googleapis.com", "artifactregistry.googleapis.com", "monitoring.googleapis.com", "logging.googleapis.com", "--project", $ProjectId)

Write-Host "Ensuring firewall rule $FirewallRuleName exists"
$firewallExists = $false
try {
  Invoke-Gcloud -Args @(
    "compute", "firewall-rules", "describe", $FirewallRuleName,
    "--project", $ProjectId
  ) | Out-Null
  $firewallExists = $true
} catch {
  $firewallExists = $false
}

if (-not $firewallExists) {
  Invoke-Gcloud -Args @(
    "compute", "firewall-rules", "create", $FirewallRuleName,
    "--allow", "tcp:8000,tcp:9090,tcp:3000",
    "--source-ranges", $SourceRanges,
    "--target-tags", $FirewallRuleName,
    "--project", $ProjectId
  )
} else {
  Write-Host "Firewall rule already exists. Updating allowed ports and source ranges."
  Invoke-Gcloud -Args @(
    "compute", "firewall-rules", "update", $FirewallRuleName,
    "--allow", "tcp:8000,tcp:9090,tcp:3000",
    "--source-ranges", $SourceRanges,
    "--target-tags", $FirewallRuleName,
    "--project", $ProjectId
  )
}

Write-Host "Ensuring instance $InstanceName exists"
$instanceExists = $false
try {
  Invoke-Gcloud -Args @(
    "compute", "instances", "describe", $InstanceName,
    "--zone", $Zone,
    "--project", $ProjectId
  ) | Out-Null
  $instanceExists = $true
} catch {
  $instanceExists = $false
}

if (-not $instanceExists) {
  Invoke-Gcloud -Args @(
    "compute", "instances", "create", $InstanceName,
    "--zone", $Zone,
    "--machine-type", $MachineType,
    "--image-family", "ubuntu-2404-lts-arm64",
    "--image-project", "ubuntu-os-cloud",
    "--boot-disk-size", "200GB",
    "--boot-disk-type", "hyperdisk-balanced",
    "--tags", $FirewallRuleName,
    "--metadata", "enable-oslogin=TRUE",
    "--project", $ProjectId
  )
} else {
  Write-Host "Instance already exists."
  Invoke-Gcloud -Args @(
    "compute", "instances", "add-metadata", $InstanceName,
    "--zone", $Zone,
    "--metadata", "enable-oslogin=TRUE",
    "--project", $ProjectId
  )
}

$repoPath = (Get-Location).Path
Write-Host ""
Write-Host "Next steps:"
Write-Host "  gcloud compute ssh $InstanceName --zone=$Zone"
Write-Host "  gcloud compute scp --recurse `"$repoPath`" ${InstanceName}:~/neuroswarm-arm --zone=$Zone"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\deploy-vm.ps1 -ProjectId $ProjectId -Zone $Zone -InstanceName $InstanceName"
