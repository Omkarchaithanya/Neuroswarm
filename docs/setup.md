# Setup (judge-zero)

Cold clone → working Axion/Compose MVP. No prior context assumed.

## Prerequisites

- Linux **aarch64** host (GCP Axion `c4a-standard-8` recommended) **or** sync to that VM from Windows via `scripts/sync-vm.ps1`
- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/)
- GGUF models under `/models` (see below)

## 1. Install deps

```bash
cd ~/neuroswarm-arm   # checkout path on Axion uses a dash
# Default sync is enough for capture/benchmarks. --all-groups needs python3-dev
# (hnswlib). If build fails: sudo apt-get install -y python3-dev && uv sync --all-groups
uv sync
cp -n .env.example .env
```

Confirm `.env` contains:

```bash
NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server
```

## 2. Models

Place (or symlink) licensed GGUFs:

```text
/models/qwen2.5-0.5b-q4_k_m.gguf
/models/llama-3.2-3b-q5_k_m.gguf
/models/llama-3.1-8b-q5_k_m.gguf
```

Helpers: `scripts/prepare-models.sh`, `scripts/upload-models.ps1`.

## 3. Build KleidiAI tiers + start stack

```bash
bash scripts/deploy-kleidiai-tiers.sh
# or: docker compose --compatibility up --build -d
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

**Pass gate:** `docker compose ps` shows `nexus-arm/llama-kleidiai:server` for tier1/2/3 — **not** `ghcr.io/ggml-org/llama.cpp:server`.

## 4. Smoke chat

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Plan a cost-optimized ARM inference demo."}],"max_tokens":256}'
```

## 5. Capture evidence (required for judges)

```bash
bash scripts/capture-evidence.sh
# Optional Performix (Arm Developer account + apx):
bash scripts/install-performix.sh
bash performix_capture.sh
```

Artifacts land in `benchmarks/results/` and a published copy under `docs/evidence/`.

## 6. Helm (after Compose works)

```bash
# Lint/template already in CI. Live install on Axion k3s (images local → aim <90s):
SKIP_BUILD=1 SKIP_LLAMA_BUILD=1 time bash scripts/deploy-k8s.sh
# or: helm upgrade --install neuroswarm ./helm/neuroswarm-arm --wait
```

Timing notes: `docs/evidence/latest/HELM-TIMING.md`.

Use release name **`neuro`** on the existing Axion k3s cluster (`helm upgrade --install neuro ./helm/neuroswarm-arm`). Do not install a second release as `neuroswarm` (annotation conflict with existing Services).

**Judge dry-run (2026-07-18):** From Windows, sync → SSH Axion → `uv sync` (not `--all-groups` unless `python3-dev` installed) → `deploy-kleidiai-tiers.sh` → `capture-evidence.sh` produced Kleidi PASS + non-empty metrics. For Instruction Mix: `sudo apt-get install -y python3-venv` then workload-based capture (`bash performix_capture.sh`; needs `--workload`, not `--system-wide`).

## Hardware honesty

Demo host is **single-NUMA Axion**. Runtime auto-detects NUMA/CXL/MTE and degrades safely; multi-socket Neoverse unlocks NUMA-split/CXL. See `01-PROBLEM-STATEMENT.md`.
