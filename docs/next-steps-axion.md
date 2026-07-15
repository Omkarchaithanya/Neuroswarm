# Next Steps: Hardened Axion VM Demo

This project is staged for the existing GCP Axion VM first, then Artifact Registry and GKE packaging. The VM checkout path is always `~/neuroswarm-arm` with a dash. Do not use `~/neuroswarm_arm`.

## Current VM

- Host alias: `neuroswarm-axion.us-central1-a.project-5bcdea88-8805-4908-991`
- Project: `project-5bcdea88-8805-4908-991`
- Zone: `us-central1-a`
- Machine: `c4a-standard-8`
- OS: Ubuntu 24.04 ARM64
- Verified CPU: Neoverse-V2 with SVE, SVE2, I8MM, and BF16

## 1. Prepare Local Environment

```powershell
uv sync --all-groups
uv run python -m compileall neuroswarm_arm packages/okf/nexus_okf benchmarks
uv run python benchmarks/run_all.py --out work\benchmarks\local-run-all.json
```

The all-in-one workflow performs those steps unless `-SkipLocalInstall` is passed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy-vm.ps1 `
  -ProjectId project-5bcdea88-8805-4908-991 `
  -Zone us-central1-a `
  -InstanceName neuroswarm-axion
```

## 2. Restrict Demo Ports

Do not leave demo ports open to `0.0.0.0/0`. Use your current public IP as `/32` when creating or updating the firewall:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-gcp.ps1 `
  -ProjectId project-5bcdea88-8805-4908-991 `
  -SourceRanges <your-public-ip>/32
```

Terraform now enforces the same rule through `infra/terraform/single-vm/variables.tf`.

For a no-public-port option later, use SSH port forwarding or GCP IAP TCP forwarding. IAP uses source range `35.235.240.0/20` for TCP forwarding to VM ports.

## 3. Copy Repo to VM

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sync-vm.ps1 -PreferGcloud
```

This copies the project to `~/neuroswarm-arm` and skips local build/cache folders. The script prefers `gcloud compute scp` when available, then falls back to plain SSH/SCP.

## 3.5 RAM constraint on `c4a-standard-8`

Host has **8 vCPU / 32 GB**. Compose uses Compose-effective `mem_limit`/`cpus` (plus `deploy` for `--compatibility`) and MVP context `4096` on all tiers. Thread defaults sum to 8 (`TIER1_THREADS=2`, `TIER2_THREADS=3`, `TIER3_THREADS=3`). Raise context or machine size (`c4a-standard-16`) only for final benchmark windows.

**Order:** sync repo → upload real models → validate → bootstrap. `deploy-vm.ps1` does not upload GGUFs; run `upload-models.ps1` separately before bootstrap.

## 4. Add Models

Copy licensed GGUF files into `/models` on the VM:

```text
/models/qwen2.5-0.5b-q4_k_m.gguf
/models/llama-3.2-3b-q5_k_m.gguf
/models/llama-3.1-8b-q5_k_m.gguf
```

From this Windows workspace, use the helper to upload the three real files from
`models/` and create those canonical aliases:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\upload-models.ps1
```

For a smoke test only, copy one tiny GGUF model and symlink it into all tiers:

```bash
cd ~/neuroswarm-arm
bash scripts/prepare-models.sh --demo-source /models/<small-demo-model>.gguf
```

Or pass the smoke model path to the deploy workflow:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy-vm.ps1 `
  -DemoModelPath /models/<small-demo-model>.gguf
```

Use real tiered models for benchmark evidence.

## 5. Validate, Bootstrap, and Run

```bash
gcloud compute ssh neuroswarm-axion --zone=us-central1-a --project=project-5bcdea88-8805-4908-991
cd ~/neuroswarm-arm
bash scripts/validate-vm.sh
bash scripts/bootstrap-vm.sh
```

If Docker group membership was just changed, reconnect SSH before running Compose without `sudo`.

## 6. Smoke Test

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8000/metrics
curl -fsS -H 'Content-Type: application/json' \
  -d '{"query":"Search the web and summarize GitHub issues for the project"}' \
  http://127.0.0.1:8000/tools/route
curl -fsS -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Create a low-cost ARM inference demo plan."}]}' \
  http://127.0.0.1:8000/v1/chat/completions
```

If firewall is restricted to your IP, open:

- Gateway: `http://35.188.21.3:8000`
- Prometheus: `http://35.188.21.3:9090`
- Grafana: `http://35.188.21.3:3000`

For SSH tunnel access instead:

```powershell
gcloud compute ssh neuroswarm-axion `
  --zone=us-central1-a `
  --project=project-5bcdea88-8805-4908-991 `
  -- -L 8000:127.0.0.1:8000 -L 9090:127.0.0.1:9090 -L 3000:127.0.0.1:3000
```

## 7. Capture Evidence

```bash
cd ~/neuroswarm-arm
bash scripts/capture-evidence.sh
```

The evidence bundle includes:

- `health.json`
- `ready.json`
- `prometheus-metrics.txt`
- `tools-route.json`
- `chat-completion.json`
- `run_all.json`
- `docker-compose-ps.txt`
- `docker-compose.log`
- `01-axion-system-info.txt`

## 8. Stop Costs

Stop the VM from the GCP Console or a machine with `gcloud` installed:

```bash
gcloud compute instances stop neuroswarm-axion --zone=us-central1-a --project=project-5bcdea88-8805-4908-991
```

## 9. Scale Later

Keep `c4a-standard-8` for the $300-credit MVP. For final benchmark windows only, consider `c4a-standard-16` or `c4a-standard-32`, then stop the VM immediately after collecting artifacts.

Defer GKE until after VM evidence is captured. When ready, use a Standard GKE Arm node pool with C4A, N4A, or Tau T2A nodes and a least-privilege node service account.
