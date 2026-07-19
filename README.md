# NeuroSwarm-Arm

NeuroSwarm-Arm is an Arm-native agent runtime for the ARM Cloud AI Optimization Challenge. The MVP runs on a single **GCP Axion** VM (`c4a-standard-8`, Neoverse-V2) and combines:

- **KleidiAI** llama.cpp CPU inference (`nexus-arm/llama-kleidiai:server`, `GGML_CPU_KLEIDIAI=ON`)
- three-tier CPU cascade routing
- semantic MCP tool selection (TurboVec ANN + hybrid rerank)
- reasoning-token governance
- HAOE Layer-1 + DIPA Layer-2 kernels
- Arm Performix closed-loop profiling (GA recipes: Code Hotspots, CPU Microarchitecture, **Instruction Mix**, Memory Access, System Characterization)
- Prometheus metrics for latency, tier usage, tool schemas, and token caps

**Topology (Option A):** HAOE/DIPA providers **auto-detect NUMA/CXL/MTE** and degrade safely on single-NUMA Axion; NUMA-split cascades and CXL KV pooling activate on multi-socket Neoverse hosts (e.g. Graviton4/5 `.16xlarge+`).

We build on Arm’s May 2026 Neoverse [SGLang contribution](https://developer.arm.com/community/arm-community-blogs/b/ai-blog/posts/bringing-sglang-high-performance-llm-inference-to-arm-neoverse) for optional CPU prefill (`SGLANG_USE_CPU_ENGINE=1`, Compose profile `pd`). **Verified:** `lmsysorg/sglang:latest` multi-arch manifest includes **linux/arm64** (`bash scripts/verify-sglang-arm64.sh`).

## Semantic MCP Tool Router

Replaces naïve injection of all MCP tool schemas with Top-K semantic routing:

`BGE-small → TurboVec → hybrid retrieval → rerank → Top-K schemas → DIPA`

```bash
pytest tests/runtime/router -q
python benchmarks/router_full.py
```

## HAOE (Layer 1)

Chat requests execute as HAOE task graphs (route → KV session → DIPA → checkpoint → response). Topology/affinity providers degrade safely on Axion (no NUMA/MTE/CXL assumptions). See [`docs/haoe/architecture.md`](docs/haoe/architecture.md).

```bash
pytest tests/runtime/haoe -q
```

## DIPA (Layer 2)

DIPA is the Inference Runtime Kernel — ASCR cascade, backends, streaming, recovery. See [`docs/dipa/architecture.md`](docs/dipa/architecture.md).

```bash
pytest tests/runtime/dipa -q
```

## Local Axion MVP

```bash
uv sync --all-groups
cp .env.example .env   # ensure NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server
bash scripts/deploy-kleidiai-tiers.sh   # on aarch64 Axion
# or: docker compose --compatibility up --build -d
```

Health:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

Evidence + Performix:

```bash
bash scripts/capture-evidence.sh
bash performix_capture.sh   # requires Arm Performix `apx`
```

Judge setup: [`docs/setup.md`](docs/setup.md). Pitch docs: `00`–`07` at repo root (Axion-true / Option A).

Deploy helpers: `scripts/sync-vm.ps1`, `scripts/deploy-vm.ps1`, `scripts/deploy-k8s.sh`.

MCP Docker image: **`armlimited/arm-mcp:latest`** (GitHub: [arm/mcp](https://github.com/arm/mcp)).
