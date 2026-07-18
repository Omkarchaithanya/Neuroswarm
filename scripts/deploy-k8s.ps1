# One-command ARM64 build + Helm install (Windows wrapper).
param(
  [string]$GatewayImage = "neuroswarm-arm-gateway:dev",
  [string]$LlamaImage = "nexus-arm/llama-kleidiai:server",
  [string]$Release = "neuro",
  [string]$ModelsHostPath = "/models",
  [string]$KindCluster = "",
  [switch]$SkipBuild,
  [switch]$SkipLlamaBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
Set-Location $Root

$env:GATEWAY_IMAGE = $GatewayImage
$env:LLAMA_IMAGE = $LlamaImage
$env:RELEASE = $Release
$env:MODELS_HOST_PATH = $ModelsHostPath
if ($KindCluster) { $env:KIND_CLUSTER = $KindCluster }
if ($SkipBuild) { $env:SKIP_BUILD = "1" }
if ($SkipLlamaBuild) { $env:SKIP_LLAMA_BUILD = "1" }

$bash = Get-Command bash -ErrorAction SilentlyContinue
if (-not $bash) {
  throw "bash is required (Git Bash or WSL). Or run scripts/deploy-k8s.sh directly."
}

& bash ./scripts/deploy-k8s.sh
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
