param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,

  [string]$Zone = "us-central1-a",
  [string]$InstanceName = "neuroswarm-obs",
  [string]$MachineType = "t2a-standard-2",
  [string]$FirewallPublic = "neuroswarm-obs-public",
  [string]$FirewallInternal = "neuroswarm-obs-internal",
  [string]$AxionInstance = "neuroswarm-axion",
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

if ($SourceRanges -eq "0.0.0.0/0") {
  throw "Refusing public 0.0.0.0/0. Pass your public IP as CIDR, e.g. -SourceRanges 203.0.113.10/32."
}

Write-Host "Setting project $ProjectId"
Invoke-Gcloud -Args @("config", "set", "project", $ProjectId)

Write-Host "Ensuring public firewall $FirewallPublic (tcp:80)"
$fwPublic = $false
try {
  Invoke-Gcloud -Args @("compute", "firewall-rules", "describe", $FirewallPublic, "--project", $ProjectId) | Out-Null
  $fwPublic = $true
} catch { $fwPublic = $false }

if (-not $fwPublic) {
  Invoke-Gcloud -Args @(
    "compute", "firewall-rules", "create", $FirewallPublic,
    "--allow", "tcp:80",
    "--source-ranges", $SourceRanges,
    "--target-tags", $FirewallPublic,
    "--project", $ProjectId
  )
} else {
  Invoke-Gcloud -Args @(
    "compute", "firewall-rules", "update", $FirewallPublic,
    "--allow", "tcp:80",
    "--source-ranges", $SourceRanges,
    "--project", $ProjectId
  )
}

Write-Host "Ensuring internal remote_write firewall $FirewallInternal (tcp:9090 from axion tag)"
$fwInternal = $false
try {
  Invoke-Gcloud -Args @("compute", "firewall-rules", "describe", $FirewallInternal, "--project", $ProjectId) | Out-Null
  $fwInternal = $true
} catch { $fwInternal = $false }

# Allow VPC-internal 9090 to obs (axion collector remote_write). Source: default VPC ranges.
if (-not $fwInternal) {
  Invoke-Gcloud -Args @(
    "compute", "firewall-rules", "create", $FirewallInternal,
    "--allow", "tcp:9090",
    "--source-ranges", "10.128.0.0/9",
    "--target-tags", $FirewallPublic,
    "--project", $ProjectId
  )
}

Write-Host "Ensuring instance $InstanceName"
$exists = $false
try {
  Invoke-Gcloud -Args @("compute", "instances", "describe", $InstanceName, "--zone", $Zone, "--project", $ProjectId) | Out-Null
  $exists = $true
} catch { $exists = $false }

if (-not $exists) {
  Invoke-Gcloud -Args @(
    "compute", "instances", "create", $InstanceName,
    "--zone", $Zone,
    "--machine-type", $MachineType,
    "--image-family", "ubuntu-2404-lts-arm64",
    "--image-project", "ubuntu-os-cloud",
    "--boot-disk-size", "50GB",
    "--boot-disk-type", "hyperdisk-balanced",
    "--tags", $FirewallPublic,
    "--project", $ProjectId
  )
} else {
  Write-Host "Instance already exists."
}

$obsIp = & gcloud compute instances describe $InstanceName --zone $Zone --project $ProjectId --format="get(networkInterfaces[0].networkIP)"
$obsExt = & gcloud compute instances describe $InstanceName --zone $Zone --project $ProjectId --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
Write-Host "Obs internal IP: $obsIp"
Write-Host "Obs external IP: $obsExt"
Write-Host "Set OBS_PROMETHEUS_REMOTE_WRITE=http://${obsIp}:9090/prometheus/api/v1/write on axion (.env)"
Write-Host "Grafana: http://${obsExt}/grafana/"
Write-Host "Prometheus: http://${obsExt}/prometheus/"
