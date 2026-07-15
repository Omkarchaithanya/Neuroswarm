# GCP Axion From-Scratch Implementation

This is the recommended hackathon path for the $300 Google Cloud trial: use one C4A Axion VM, run all inference on CPU with llama.cpp, and prove cost reduction through cascade routing, semantic tool filtering, and reasoning-token caps.

## 1. Set Up Google Cloud

Use `projectId`, not display name.

Example from this project:

- project name: `My First Project`
- project ID: `project-5bcdea88-8805-4908-991`

If you need to find it again:

```bash
gcloud projects list --format="table(name,projectId,projectNumber)"
```

Then select exact ID:

```bash
gcloud auth login
gcloud config set project project-5bcdea88-8805-4908-991
gcloud services enable compute.googleapis.com artifactregistry.googleapis.com
```

Create a restricted firewall rule for demo ports. Replace `<your-public-ip>/32`; do not use `0.0.0.0/0` for normal testing:

```bash
gcloud compute firewall-rules create neuroswarm-demo \
  --allow tcp:8000,tcp:9090,tcp:3000 \
  --source-ranges <your-public-ip>/32 \
  --target-tags neuroswarm-demo
```

## 2. Create Axion VM

Create C4A ARM VM:

```bash
gcloud compute instances create neuroswarm-axion \
  --zone=us-central1-a \
  --machine-type=c4a-standard-8 \
  --image-family=ubuntu-2404-lts-arm64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=200GB \
  --boot-disk-type=hyperdisk-balanced \
  --tags=neuroswarm-demo
```

SSH into it:

```bash
gcloud compute ssh neuroswarm-axion --zone=us-central1-a
```

Verify ARM:

```bash
uname -m
lscpu
grep -E 'asimd|sve|sve2|i8mm|dotprod|bf16' /proc/cpuinfo | sort -u
```

Save result:

```bash
mkdir -p benchmarks/results
(uname -m; lscpu; grep -E 'asimd|sve|sve2|i8mm|dotprod|bf16' /proc/cpuinfo | sort -u) \
  > benchmarks/results/01-axion-system-info.txt
```

## 3. Install Runtime Tools

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates build-essential cmake clang libcurl4-openssl-dev docker.io docker-compose-plugin
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
```

## 4. Copy Project

On laptop, copy the repo to the canonical remote path:

```bash
gcloud compute scp --recurse neuroswarm-arm neuroswarm-axion:~/neuroswarm-arm --zone=us-central1-a
```

On VM:

```bash
cd ~/neuroswarm-arm
cp .env.example .env
```

If using the PowerShell helper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sync-vm.ps1 -PreferGcloud
```

## 5. Prepare Models

Create model directory:

```bash
sudo mkdir -p /models
sudo chown "$USER:$USER" /models
```

Expected GGUF files:

| File | Purpose |
|---|---|
| `/models/qwen2.5-0.5b-q4_k_m.gguf` | Tier 1 drafter |
| `/models/llama-3.2-3b-q5_k_m.gguf` | Tier 2 verifier |
| `/models/llama-3.1-8b-q5_k_m.gguf` | Tier 3 arbiter |

For first demo, you can point all three filenames at one tiny GGUF model with symlinks. For final scoring, use three real tiers.

```bash
bash scripts/prepare-models.sh --demo-source /models/<small-demo-model>.gguf
```

## 6. Start Stack

```bash
docker compose up --build -d
docker compose ps
```

Health:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

Tool routing:

```bash
curl -s http://127.0.0.1:8000/tools/route \
  -H 'Content-Type: application/json' \
  -d '{"query":"Search the web and summarize GitHub issues for the project"}'
```

Chat:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "messages":[{"role":"user","content":"Design a low-cost ARM inference benchmark plan."}],
    "max_tokens":256,
    "temperature":0.2,
    "agent_role":"reasoning"
  }'
```

Expected fields:

- `id`
- `object`
- `tier_used`
- `tool_schemas_used`
- `thinking_token_cap`
- `choices[0].message.content`
- `usage.total_tokens`
- `metrics.latency_ms`
- `metrics.quant_policy`

## 7. Observe Metrics

Prometheus:

```text
http://VM_EXTERNAL_IP:9090
```

Gateway metrics:

```bash
curl http://127.0.0.1:8000/metrics
```

## 8. Benchmark Claims

```bash
uv sync --all-groups
uv run python benchmarks/run_all.py --out benchmarks/results/run_all.json
```

Set `NSA_VM_HOURLY_COST_USD` in `.env` before running the economics benchmark if you want a dollar estimate instead of the normalized placeholder.

## 9. Cost Controls

- Stop VM when not benchmarking.
- Use `c4a-standard-8` for initial development.
- Keep model disks small.
- Capture screenshots, JSON outputs, and terminal logs.

Stop:

```bash
gcloud compute instances stop neuroswarm-axion --zone=us-central1-a
```

Delete:

```bash
gcloud compute instances delete neuroswarm-axion --zone=us-central1-a
```

## 10. Demo Flow

1. Show Axion hardware verification.
2. Show llama.cpp CPU-only tiers.
3. Send one request to `/v1/chat/completions`.
4. Highlight `tier_used`, `tool_schemas_used`, `thinking_token_cap`.
5. Show Prometheus metrics.
6. Show benchmark JSON for cascade, router, governor, economics.
7. Mention future work: CXL KV cache, MTE sharing, RL tuning, Helm/GKE.
