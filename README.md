# NeuroSwarm-Arm

**Live Status (GCP `neuroswarm-axion`, Neoverse-V2) — from live `/ready` 2026-08-03**

```
embedding_backend=fastembed  dims=384  tools_indexed=42
build-info: SVE2+I8MM present; SME2 not available
router accuracy: top1=1.0 top3=1.0 top5=1.0  reduction≈0.89 (schema-token ratio, not 40→3/92%)
MCP execute: ON (default in 1.x; compose NSA_MCP_EXECUTE=1)
MCP manager: protocol 2025-11-25; tools_executable=29 after tools/list reconcile
tool_cache GET /v1/tools/cache: 404 on live gateway (Layer-2 speculative endpoints not redeployed yet)
```

NeuroSwarm-Arm is an Arm-native agent runtime for the ARM Cloud AI Optimization Challenge. The MVP runs on a single GCP Axion VM and combines:

- llama.cpp CPU inference on Arm64
- three-tier CPU cascade routing
- semantic MCP tool selection (TurboVec ANN when the wheel is active + hybrid rerank; exact NumPy fallback — see [`neuroswarm_arm/runtime/router/docs/`](neuroswarm_arm/runtime/router/docs/))
- reasoning-token governance
- adaptive quantization policy metadata
- HAOE Layer-1 runtime kernel (task graphs, work stealing, affinity HAL, telemetry)
- DIPA Layer-2 inference runtime kernel (planner, **ASCR** cascade, backends, streaming, recovery)
- Speculative tool calling (predict → overlap MCP → `ToolOutputCache`; see Key Components)
- Prometheus metrics for latency, tier usage, tool schemas, and token caps

## Acronym map (5-plane stack)

| Acronym | One-liner |
|---------|-----------|
| **HAOE** | Layer-1 task-graph runtime (schedules work; never runs models) |
| **DIPA** | Layer-2 inference kernel (planner → routers → cascade → backends) |
| **ASCR** | Adaptive speculative / quality cascade across CPU tiers |
| **AROP** | Evolution / runtime optimization loop (Performix-fed policies) |
| **OKF** | Ontology / knowledge files compiled into agent context |
| **AQR** | Adaptive quantization routing metadata |
| **AWPP** | Arm weight / preference policy connector |
| **MAKS** | Memory / KV session services |
| **RTG** | Reasoning-token governor |
| **ACR** | Agent conversation / memory recall plane |

## Latency Performance

**Arm Performix evidence (in-repo):** [`docs/evidence/performix/OPTIMIZATIONS.md`](docs/evidence/performix/OPTIMIZATIONS.md) — Code Hotspots (`source=apx`, `libggml-cpu` ~79%) + Kleidi vs stock Instruction Mix + flame PNG. Runtime `work/performix/` is gitignored; judges use the docs pack.

Baseline checklist showed tier1 chat ~**1116ms** while `haoe_workflow_latency_ms` ~**1970ms** (~850ms orchestration overhead on a non-escalating turn). Mitigations in this tree:

1. **MCP process pool** — warm stdio servers instead of spawn-per-call (`mcp_executor.py`)
2. **HAOE fast-path** — high-confidence chat skips full `submit_workflow` DAG (`gateway.py`, `metrics.haoe_bypassed=true`)
3. **ASCR round-1** — skip threshold recompute on first round; `NSA_ASCR_MAX_ROUNDS` for demo measurement (default remains 4)

Router gates stay at top1=1.0 (`threshold=0.42`, `high_conf_gate=0.70`) — not tuned for speed.

**Speculative tool calling (measured, `mode=inproc`):** from [`benchmarks/results/speculative_tool_bench.json`](benchmarks/results/speculative_tool_bench.json) — not a live-gateway Axion A/B yet:

| Metric | Value |
|--------|------:|
| hit_rate | 0.5 |
| avg_time_saved_ms | 45.185 |
| p50 time_saved_ms | 49.245 |
| p95 time_saved_ms | 80.785 |
| mean_latency_baseline_ms | 150.894 |
| mean_latency_speculative_ms | 105.825 |
| tokens_per_dollar_delta | 650287.45 |

Reproduce: `python benchmarks/speculative_tool_bench.py` (or `make bench-tool-spec`).

## Key Components

### Semantic MCP Tool Router

Replaces naïve injection of all MCP tool schemas with Top-K semantic routing:

`BGE-small → TurboVec (2/4-bit TurboQuant when active; else exact NumPy) → hybrid retrieval → rerank → Top-K schemas → DIPA`

Default `NSA_ROUTER_TURBOVEC_MIN_TOOLS=0` so TurboVec runs whenever the ARM64 wheel imports. `/ready` reports honest `configured_backend` / `active_backend` / `fallback_reason`. Advertised tool YAML IDs match FastMCP execute names (`scripts/verify-mcp-execute-contract.py`).

```bash
pytest tests/runtime/router -q
python benchmarks/router_full.py
```

### HAOE (Layer 1)

Chat requests execute as HAOE task graphs (route → KV session → DIPA → checkpoint → response). High-confidence turns may take the gateway fast-path (cascade direct). HAOE coordinates inference; it does not run models. Topology/affinity providers degrade safely on Axion (no NUMA/MTE/CXL assumptions). See [`docs/haoe/architecture.md`](docs/haoe/architecture.md) and ADRs under `docs/haoe/adr/`.

```bash
pytest tests/runtime/haoe -q
```

### DIPA (Layer 2)

DIPA is the Inference Runtime Kernel. Agents never call llama.cpp / vLLM / ExecuTorch / LiteRT directly — everything flows through DIPA (execution planner → model/backend/quant routers → **ASCR** → prefill/decode → streaming → metrics). AQR / AWPP / MAKS are connectors only. See [`docs/dipa/architecture.md`](docs/dipa/architecture.md) and [`docs/armcascade/`](docs/armcascade/README.md).

On Apple Silicon (M3/M4/M5), install the optional MLX backend:

```bash
uv sync --extra apple
```

See [`docs/dipa/mlx.md`](docs/dipa/mlx.md) for Metal setup, model conversion, and speculative decoding via `mlx_lm.server`.

```bash
pytest tests/runtime/dipa -q
```

### Speculative Tool Calling

Overlaps a draft **tool prediction** with the main cascade generation so MCP work can finish (or hit cache) before the actor emits the real `tool_call`. This is **tool-level** speculation (not token draft/verify ASCR). Cache keys are canonical via `ToolOutputCache.make_key(tool_name, args)` → `sha256(f"{tool}:{canonical_json(args)}")[:32]` in [`neuroswarm_arm/runtime/dipa/speculative/tool_cache.py`](neuroswarm_arm/runtime/dipa/speculative/tool_cache.py).

Draws on [arXiv:2512.15834](https://arxiv.org/abs/2512.15834) (Nichols et al., Speculative Tool Calling) and [arXiv:2510.04371](https://arxiv.org/abs/2510.04371) (Ye et al., Speculative Actions). Engine algorithm lives in [`neuroswarm_arm/runtime/dipa/speculative/engine.py`](neuroswarm_arm/runtime/dipa/speculative/engine.py) (Prompt B4 / paper §4).

See it work (after gateway rebuild with `NSA_TOOL_SPEC_ENABLED=1`, default in compose 1.x):

```bash
curl -s http://127.0.0.1:8000/v1/tools/cache
curl -s http://127.0.0.1:8000/v1/tools/spec_debug
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Use echo.add to compute 2 + 3"}],"max_tokens":128}'
```

```text
query ──► predictor(T1) ──► executor(MCP) ──► cache
                     │                ▲
                     ▼                │
                 main gen(T2/3) ──► if tool_call matches, use cached
```

## Local Axion MVP

```bash
uv sync --all-groups
cp .env.example .env   # Linux/macOS; on Windows: Copy-Item .env.example .env
docker compose up --build
```

The gateway listens on `http://VM_EXTERNAL_IP:8000`.

Health check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/v1/tools/cache
```

Chat request:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Plan a cost-optimized ARM inference demo."}],"max_tokens":256}'
```

The response now includes OpenAI-style `choices` and `usage` fields in addition to the project-specific cascade metadata.

Detailed from-scratch setup is in `docs/gcp-axion-setup.md`.

For repeatable GCP setup, use:

- `scripts/bootstrap-gcp.ps1`
- `scripts/bootstrap-vm.sh`

Initial dev target: `c4a-standard-8` with `hyperdisk-balanced`.
