# Tech Stack — Concrete Tools, Versions, Build Flags

> All components, exact repos, exact build flags, exact Arm Performix recipes. Copy-paste ready.

---

## Hardware target

**Primary:** AWS Graviton5 `m9g.4xlarge` (or `c9g.4xlarge` compute-optimized, or `r9g` memory-optimized if available).
- 192 Neoverse V3 cores (we'll use 16-32)
- DDR5-8800, 12 channels
- 192 MB L3 (5× Graviton4)
- 3 nm, Armv9.2-A + SVE2 128-bit + I8MM + DotProd + BF16

**Fallback during dev:** AWS Graviton4 `c8g.4xlarge` (16 vCPU, DDR5-5600). Neoverse V2, still has SVE2 + I8MM. Most of the optimizations transfer.

**Future-proof target:** Arm AGI CPU dev-kit (136 cores, native CXL 3.0). Note in submission as the production path for 2027.

---

## Software inventory

### Build base
| Component | Version | Source | Notes |
|---|---|---|---|
| Ubuntu | 24.04 LTS | AWS Marketplace | aarch64 |
| GCC | 13+ | apt | for `-march=armv9.2-a+sve2+i8mm+dotprod` |
| Clang | 17+ | apt | preferred for SVE2 codegen |
| CMake | 3.28+ | source build | required for KleidiAI flags |
| Python | 3.12 | apt | for orchestration layer |

### Inference engines
| Component | Repo | Branch/Tag | Build |
|---|---|---|---|
| **llama.cpp** | https://github.com/ggml-org/llama.cpp | master (or b4500+) | With KleidiAI = ON |
| **KleidiAI** | https://gitlab.arm.com/kleidi/kleidiai | latest | linked into llama.cpp via XNNPack |
| **XNNPack** | https://github.com/google/XNNPACK | latest | already linked from KleidiAI |
| **vLLM** | https://github.com/vllm-project/vllm | v0.6+ | INT4 path on Arm |
| **ExecuTorch** | https://github.com/pytorch/executorch | 0.7+ | KleidiAI default |

### Agent frameworks (we wrap, not rebuild)
| Component | Repo | Use |
|---|---|---|
| LangGraph | https://github.com/langchain-ai/langgraph | agent graph runtime |
| llama-cpp-agent | https://github.com/Maximilian-Winter/llama-cpp-agent | bridge to llama.cpp |

### Memory / routing / cost
| Component | Repo / Source |
|---|---|
| **Mem0** | https://github.com/mem0ai/mem0 |
| **Mem0 MCP server** | https://github.com/mem0ai/mem0-mcp |
| **Open Knowledge Format** | https://github.com/google/open-knowledge-format (spec) |
| **FAISS** | https://github.com/facebookresearch/faiss | ARM64 wheels available |
| **BGE-small-en-v1.5** | HuggingFace (BAAI/bge-small-en-v1.5) | 90 MB embedding model |

### Profiling (REQUIRED by hackathon)
| Component | Source |
|---|---|
| **Arm Performix** | https://developer.arm.com/servers-and-cloud-computing/arm-performix (free download) |
| **Arm MCP Server** | https://github.com/arm/mcp (Docker Hub: `armlimited/arm-mcp`) — IDE/stdio toolbox; product AROP uses `performix-bridge` |
| **Arm Kleidi learning paths** | https://learn.arm.com/learning-paths/servers-and-cloud-computing/ |

### Orchestration
| Component | Source |
|---|---|
| **FastAPI** | https://github.com/tiangolo/fastapi |
| **uvicorn** | pip |
| **Prometheus** + **Grafana** | official images |
| **Helm** | for K8s/EKS deployment |
| **Docker buildx** | for ARM64 multi-arch |

---

## Build script — llama.cpp + KleidiAI (drop into Dockerfile)

```dockerfile
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    build-essential cmake git wget curl python3 python3-pip \
    libopenblas-dev libssl-dev libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Build KleidiAI
RUN git clone --depth 1 https://gitlab.arm.com/kleidi/kleidiai.git /opt/kleidiai \
    && cd /opt/kleidiai \
    && mkdir build && cd build \
    && cmake .. -DCMAKE_BUILD_TYPE=Release \
                -DCMAKE_C_FLAGS="-mcpu=native -march=armv9.2-a+sve2+i8mm+dotprod+bf16 -O3" \
                -DCMAKE_CXX_FLAGS="-mcpu=native -march=armv9.2-a+sve2+i8mm+dotprod+bf16 -O3" \
    && make -j$(nproc) install

# Build llama.cpp with KleidiAI
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp \
    && cd /opt/llama.cpp \
    && mkdir build && cd build \
    && cmake .. \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang \
        -DCMAKE_CXX_COMPILER=clang++ \
        -DCMAKE_C_FLAGS="-mcpu=native -march=armv9.2-a+sve2+i8mm+dotprod+bf16 -mtune=neoverse-v3 -O3 -ffast-math -fopenmp" \
        -DCMAKE_CXX_FLAGS="-mcpu=native -march=armv9.2-a+sve2+i8mm+dotprod+bf16 -mtune=neoverse-v3 -O3 -ffast-math -fopenmp" \
        -DGGML_CPU_KLEIDIAI=ON \
        -DGGML_NATIVE=ON \
        -DGGML_OPENMP=ON \
        -DGGML_CPU_ALL_VARIANTS=ON \
    && make -j$(nproc) \
    && make install

# Verify SVE2 + I8MM + DotProd present
RUN grep -E '^(Features|sve2|i8mm|dotprod|bf16|asimd)' /proc/cpuinfo | sort -u
```

**nproc must equal vCPU count** — default llama.cpp uses half the cores, leading to massive underperformance. Document this in the README.

---

## Model inventory (GGUF checkpoints)

| Tier | Model | Quant | Size | Source |
|---|---|---|---|---|
| 1 (drafter) | Qwen2.5-0.5B-Instruct | Q4_K_M | ~400 MB | HF bartowski |
| 2 (verifier) | Llama-3.2-3B-Instruct | Q5_K_M | ~2.4 GB | HF bartowski |
| 3 (arbiter) | Llama-3.1-8B-Instruct | Q5_K_M | ~5.5 GB | HF bartowski |
| 3R (reasoning) | DeepSeek-R1-Distill-Llama-8B | Q5_K_M | ~5.5 GB | HF |
| Embed | BGE-small-en-v1.5 | (ONNX int8) | ~90 MB | HF BAAI |

**Total disk:** ~14 GB. Fits in 128 GB RAM with room for KV caches.

**Quantization command (already done by bartowski, but for completeness):**

```bash
# Convert HF → GGUF
python convert_hf_to_gguf.py /path/to/Llama-3.1-8B-Instruct --outfile llama-3.1-8b-f16.gguf

# Quantize to Q5_K_M
./llama-quantize llama-3.1-8b-f16.gguf llama-3.1-8b-q5_k_m.gguf Q5_K_M
```

---

## Arm Performix recipes we'll run

**Primary Neuroswarm path:** install `apx` **on the Axion target** (see `scripts/install-performix.sh`). Windows Performix GUI is optional (SSH Targets → Axion for interactive exploration only).

Current CLI (2026 Performix) — **no** `--output` / `--binary` / `prepare local`:

```bash
apx target prepare
apx recipe run code_hotspots --system-wide --timeout 60 --deploy-tools --json
# parse run_id from NDJSON even if RC!=0, then:
apx run export <run_id> /tmp/apx-export --json
# normalize → work/performix/snapshot.json with source=apx
NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 PERFORMIX_DURATION=60 \
  bash scripts/refresh-performix-snapshot.sh
```

Recipe ids use underscores (`code_hotspots`, `cpu_microarchitecture`, `system_utilization`). Hyphen aliases are normalized in `PerformixClient`.

Optional compare (best-effort; flags may vary by `apx` build):

```bash
apx recipe compare --help
```

---

## Arm MCP Server integration

**Do not conflate:**

| Surface | Image / URL | Role |
|---------|-------------|------|
| Product AROP MCP | `performix-bridge:8090` | HTTP `/mcp` wrapping **host** `apx` |
| Official Arm MCP | `armlimited/arm-mcp` ([arm/mcp](https://github.com/arm/mcp)) | IDE stdio: `kb_search`, migrate, Performix-over-SSH |

```bash
# Product path (Compose)
export NSA_AROP_PERFORMIX_MCP=http://performix-bridge:8090
docker compose --profile performix up -d performix-bridge gateway

# Optional IDE-only (see .cursor/mcp.json.example)
docker pull armlimited/arm-mcp:latest
```

Official Arm MCP tools (IDE): `kb_search`, migrate analysis, container inspect, assembly/LLVM-MCA, Performix-over-SSH — **not** wired as the Compose AROP default.
---

## Helm chart structure

```
helm/neuroswarm-arm/
├── Chart.yaml
├── values.yaml                  # defaults: 3 replicas, 16 vCPU each
├── templates/
│   ├── neuroswarm-router.yaml   # HAOE + cost router deployment
│   ├── tier1-drafter.yaml       # llama-server Qwen2.5-0.5B
│   ├── tier2-verifier.yaml      # llama-server Llama-3.2-3B
│   ├── tier3-arbiter.yaml       # llama-server Llama-3.1-8B
│   ├── semantic-router.yaml     # BGE-small + FAISS
│   ├── mem0.yaml                # Mem0 vector store
│   ├── prometheus.yaml          # scrape config
│   ├── grafana.yaml             # dashboards
│   ├── pvc.yaml                 # KV-cache + OKF storage
│   └── service.yaml             # FastAPI gateway
└── README.md
```

**Install:**
```bash
helm install neuro ./helm/neuroswarm-arm \
  --set graviton.instance=m9g.4xlarge \
  --set cascade.kDraft=5 \
  --set governor.thinkingTokenMax=2048
```

---

## MCP server templates (6 ready-to-run)

Each template is a directory with a Dockerfile + Python entrypoint + OKF metadata:

```
templates/mcp-servers/
├── github/         # GitHub API: issues, PRs, code search
├── postgres/       # SQL queries with safety wrapper
├── s3/             # Read/write objects
├── slack/          # Channel + DM messaging
├── web-search/     # Brave/Google search
└── browser/        # Headless browser via Playwright
```

Each includes:
- `Dockerfile` (ARM64, python:3.12-slim)
- `server.py` (FastMCP tools)
- `okf-metadata.yaml` (tool name, description, parameters — feeds the semantic router)
- `test_agent.py` (verifies it works with NeuroSwarm-Arm)

---

## Cost dashboard (Grafana JSON)

Pre-built dashboard panels:
1. Tokens/sec (live, 24h sparkline)
2. Cost per 1M tokens (vs. H100 spot baseline)
3. Cascade hit-rate donut chart (Tier 1 / 2 / 3 / fallback)
4. KV cache memory utilization + dedup ratio
5. Average thinking tokens per query (vs. baseline)
6. ARM PMU: SIMD utilization, memory bandwidth, branch miss rate
7. Performix hotspots top-10 (auto-refreshed)
8. Agent swarm topology map (which agent is on which core)
9. Cost saved per hour (cumulative)

---

## Verification checklist (must pass before submission)

- [ ] `apx recipe run code-hotspots` produces a flame graph with ggml I8MM kernels visible
- [ ] `grep -E '(sve2|i8mm|dotprod|bf16)' /proc/cpuinfo` returns all four
- [ ] llama.cpp `--version` reports KleidiAI enabled
- [ ] Cascade baseline → cascade shows ≥1.8× speedup in benchmark
- [ ] Semantic router → top-3 tool accuracy ≥95% on MCPGA ground truth
- [ ] Reasoning governor → ≤2,500 thinking tokens avg on DeepSeek-R1 test
- [ ] CXL KV pool → 200k-token session survives worker restart (re-attach)
- [ ] Helm install neuro → dashboard accessible in <90s
- [ ] Cost dashboard → live $/1M tokens vs. H100 baseline
- [ ] Demo video → <3 min, on real Graviton5, public YouTube

---

## Links to consult while building

| Topic | URL |
|---|---|
| Arm Performix | https://developer.arm.com/servers-and-cloud-computing/arm-performix |
| Arm MCP Server | https://github.com/arm/mcp |
| llama.cpp Arm build | https://learn.arm.com/learning-paths/servers-and-cloud-computing/llama-cpu/llama-chatbot/ |
| llama.cpp Kleidi chatbot | https://learn.arm.com/learning-paths/servers-and-cloud-computing/llama-cpu/_demo/ |
| Performix MCP agent | https://learn.arm.com/learning-paths/servers-and-cloud-computing/performix-mcp-agent/ |
| Distributed llama.cpp | https://learn.arm.com/learning-paths/servers-and-cloud-computing/distributed-inference-with-llama-cpp/ |
| ExecuTorch + KleidiAI | https://pytorch.org/blog/bringing-generative-ai-to-the-masses-with-executorch-and-kleidiai/ |
| vLLM INT4 on Arm | https://learn.arm.com/learning-paths/servers-and-cloud-computing/vllm-int4/ (Track 2 path) |
| rtp-llm on Arm | (Track 2 learning path) |