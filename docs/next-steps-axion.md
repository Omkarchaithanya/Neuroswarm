# Next Steps: Hardened Axion VM Demo

This project is staged for the existing GCP Axion VM first, then Artifact Registry and GKE packaging. The VM checkout path is always `~/neuroswarm-arm` with a dash. Do not use `~/neuroswarm_arm`.

## Current VM (placeholders — ask operator for live IDs)

> **Public-repo scrub:** project ID, zone hostname, and external IP are **not** committed. Set them via env / gcloud config / local secrets.

```bash
export GCP_PROJECT="<your-gcp-project-id>"
export GCP_ZONE="<zone e.g. us-central1-a>"
export GCP_INSTANCE="neuroswarm-axion"
# Optional: VM_EXTERNAL_IP from `gcloud compute instances describe ...`
```

- Machine: `c4a-standard-8`
- OS: Ubuntu 24.04 ARM64
- Verified CPU: Neoverse-V2 with SVE, SVE2, I8MM, and BF16
- Topology: **1 NUMA node** (Option A adaptive orchestration — no NUMA-split claim on this box)

## 1. Prepare Local Environment

```powershell
uv sync --all-groups
uv run python -m compileall neuroswarm_arm packages/okf/nexus_okf benchmarks
uv run python benchmarks/run_all.py --out work\benchmarks\local-run-all.json
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy-vm.ps1 `
  -ProjectId $env:GCP_PROJECT `
  -Zone $env:GCP_ZONE `
  -InstanceName neuroswarm-axion
```

## 2. Restrict Demo Ports

Do not leave demo ports open to `0.0.0.0/0`. Use your current public IP as `/32`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-gcp.ps1 `
  -ProjectId $env:GCP_PROJECT `
  -SourceRanges <your-public-ip>/32
```

Terraform enforces the same via `infra/terraform/single-vm/variables.tf`.  
Prefer SSH / IAP tunnels for demos. IAP TCP source: `35.235.240.0/20`.

## 3. Copy Repo to VM

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sync-vm.ps1 -PreferGcloud
```

Checkout lands at `~/neuroswarm-arm`.

## 3.5 RAM constraint on `c4a-standard-8`

Host has **8 vCPU / 32 GB**. Thread defaults sum to 8; MVP ctx 4096.  
**Order:** sync → `upload-models.ps1` → validate → bootstrap → **`deploy-kleidiai-tiers.sh`**.

## 4. Add Models

```text
/models/xLAM-2-1B-fc-r-Q4_0.gguf
/models/xLAM-2-3B-fc-r-Q4_0.gguf
/models/DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\upload-models.ps1
```

## 5. Validate, Bootstrap, KleidiAI

```bash
gcloud compute ssh "$GCP_INSTANCE" --zone="$GCP_ZONE" --project="$GCP_PROJECT"
cd ~/neuroswarm-arm
bash scripts/validate-vm.sh
bash scripts/bootstrap-vm.sh
bash scripts/deploy-kleidiai-tiers.sh
```

## 6. Smoke Test

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8000/metrics
curl -fsS -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Create a low-cost ARM inference demo plan."}],"max_tokens":128}' \
  http://127.0.0.1:8000/v1/chat/completions
```

External URL: `http://<VM_EXTERNAL_IP>:8000` only if firewall allows your `/32`. Prefer tunnel:

```powershell
gcloud compute ssh neuroswarm-axion `
  --zone=$env:GCP_ZONE `
  --project=$env:GCP_PROJECT `
  -- -L 8000:127.0.0.1:8000 -L 9090:127.0.0.1:9090 -L 3000:127.0.0.1:3000
```

## 7. Capture Evidence

```bash
cd ~/neuroswarm-arm
bash scripts/capture-evidence.sh
bash performix_capture.sh   # Arm account + apx
```

Expect KleidiAI IMAGE in `docker-compose-ps.txt`, non-empty metrics, non-skipped `run_all.json`. Published copy: `docs/evidence/latest/`.

## 8. Stop Costs

```bash
gcloud compute instances stop "$GCP_INSTANCE" --zone="$GCP_ZONE" --project="$GCP_PROJECT"
```

## 9. Scale Later

Keep `c4a-standard-8` for MVP. Larger C4A only for final bench windows. Defer GKE until VM evidence is solid (`scripts/deploy-k8s.sh`).
