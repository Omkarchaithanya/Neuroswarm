# NEXUS-ARM Step-by-Step Implementation Guide

## 0. Build Target

Implement NEXUS-ARM / NeuroSwarm-Arm as a practical Arm-native multi-agent runtime with these deliverables:

1. Arm-optimized llama.cpp inference on Graviton.
2. CPU-CPU speculative cascade.
3. FastAPI routing proxy for agent requests.
4. Semantic MCP tool router.
5. Reasoning-token governor.
6. Adaptive quantization policy.
7. Mem0 / OKF memory layer.
8. KV-cache persistence with NVMe fallback first, CXL path second.
9. Performix benchmark loop.
10. Prometheus + Grafana cost dashboard.
11. Docker ARM64 image and Helm chart.
12. Reproducible benchmark scripts.

Keep the first working version smaller than the full vision: cascade + semantic router + governor + Performix + dashboard. Add MTE/CXL/RL evolution after the measurable MVP works.

## 1. Create Repository Structure

Create this structure first:

```text
neuroswarm-arm/
  app/
    main.py
    config.py
    schemas.py
    gateway.py
    router.py
    governor.py
    aqr.py
    metrics.py
    inference/
      llama_client.py
      cascade.py
      dipa.py
    tools/
      semantic_mcp_router.py
      registry.py
    memory/
      mem0_client.py
      okf_loader.py
      kv_pager.py
    evolution/
      performix_client.py
      evolution_loop.py
  native/
    json_sve2.c
    mte_kv.c
    CMakeLists.txt
  okf/
    index.md
    agents/
    tools/
    policies/
  templates/
    mcp-servers/
      github/
      postgres/
      s3/
      slack/
      web-search/
      browser/
  benchmarks/
    recipes/
    test-data/
    run_all.sh
    cascade_acceptance.py
    router_accuracy.py
    governor_tokens.py
    economics.py
  helm/
    neuroswarm-arm/
  docs/
    setup.md
    reproduce-benchmarks.md
    migrate-from-gpu.md
  Dockerfile.arm64
  docker-compose.yaml
  pyproject.toml
  README.md
  LICENSE
```

## 2. Provision Arm Machine

Use AWS Graviton5 if available. If not, use Graviton4.

```bash
uname -m
lscpu
numactl --hardware
grep -E 'sve2|i8mm|dotprod|bf16|asimd' /proc/cpuinfo | sort -u
```

Acceptance criteria:

- Architecture is `aarch64`.
- SVE2 / I8MM / DotProd / BF16 are visible where supported.
- NUMA topology is captured.
- Hardware details are saved to `benchmarks/01-system-info.txt`.

## 3. Build llama.cpp with KleidiAI

Create `Dockerfile.arm64` using Ubuntu 24.04 and build llama.cpp with:

```bash
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_C_FLAGS="-mcpu=native -march=armv9.2-a+sve2+i8mm+dotprod+bf16 -mtune=neoverse-v3 -O3 -ffast-math -fopenmp" \
  -DCMAKE_CXX_FLAGS="-mcpu=native -march=armv9.2-a+sve2+i8mm+dotprod+bf16 -mtune=neoverse-v3 -O3 -ffast-math -fopenmp" \
  -DGGML_CPU_KLEIDIAI=ON \
  -DGGML_NATIVE=ON \
  -DGGML_OPENMP=ON \
  -DGGML_CPU_ALL_VARIANTS=ON
```

Acceptance criteria:

- `llama-cli --version` works.
- `llama-bench` runs on Arm.
- README records the exact build flags.
- A smoke prompt completes with the Tier 1 model.

## 4. Download and Place Models

Use these model tiers:

| Tier | Purpose | Model | Quant |
|---|---|---|---|
| Tier 1 | Drafter | Qwen2.5-0.5B-Instruct | Q4_K_M |
| Tier 2 | Verifier | Llama-3.2-3B-Instruct | Q5_K_M |
| Tier 3 | Arbiter | Llama-3.1-8B-Instruct | Q5_K_M |
| Reasoning | Optional | DeepSeek-R1-Distill-Llama-8B | Q5_K_M |
| Embedding | Tool routing | BGE-small-en-v1.5 | ONNX/int8 or CPU sentence-transformers |

Place model paths in `app/config.py`.

Acceptance criteria:

- Each configured model path exists.
- Tier 1, Tier 2, and Tier 3 can run independently.

## 5. Start Baseline llama.cpp Server

Run one non-cascade server first:

```bash
llama-server \
  -m /models/llama-3.1-8b-q5_k_m.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  -ngl 0 \
  -t 16 \
  -c 8192
```

Create `benchmarks/baseline_llama.py` to measure:

- time to first token
- decode tokens/sec
- total latency
- input/output tokens

Acceptance criteria:

- Baseline JSON is written to `benchmarks/results/baseline.json`.
- This becomes the comparison target for all later optimizations.

## 6. Implement CPU-CPU Cascade

Start separate servers:

```bash
numactl --cpunodebind=0 --membind=0 \
  llama-server -m /models/qwen2.5-0.5b-q4_k_m.gguf \
  --port 8081 -ngl 0 -t 16 -c 4096

numactl --cpunodebind=1 --membind=1 \
  llama-server -m /models/llama-3.2-3b-q5_k_m.gguf \
  --port 8082 -ngl 0 -t 16 -c 8192

numactl --interleave=all \
  llama-server -m /models/llama-3.1-8b-q5_k_m.gguf \
  --port 8083 -ngl 0 -t 32 -c 16384
```

Implement `app/inference/llama_client.py`:

- `chat(port, messages, max_tokens, temperature)`
- `complete(port, prompt, max_tokens)`
- timeout handling
- metrics collection

Implement `app/inference/cascade.py`:

1. Send query to Tier 1.
2. Estimate confidence from logprobs if available, otherwise use heuristic checks.
3. If confidence >= threshold, accept Tier 1.
4. If confidence is medium, call Tier 2.
5. If confidence is low or reasoning is required, call Tier 3.
6. Record selected tier, latency, tokens, and cost.

Acceptance criteria:

- `/v1/chat/completions` can route through the cascade.
- Each response includes `tier_used`.
- Benchmark shows speedup or clear fallback behavior.

## 7. Build FastAPI Gateway

Implement `app/main.py`:

```text
POST /v1/chat/completions
GET  /health
GET  /metrics
POST /tools/register
POST /tools/route
POST /bench/run
```

Request flow:

1. Receive user query.
2. Route tools with semantic MCP router.
3. Compute reasoning budget with governor.
4. Select quant/tier with AQR and cost router.
5. Call cascade.
6. Return answer plus telemetry.
7. Export metrics to Prometheus.

Acceptance criteria:

- Gateway can replace direct llama-server calls.
- Prometheus metrics expose latency, tokens, tier, cost, and tool count.

## 8. Implement Semantic MCP Tool Router

Implement `app/tools/registry.py`:

- Stores tool name, description, params, endpoint, auth type.
- Loads initial tools from `templates/mcp-servers/*/okf-metadata.yaml`.

Implement `app/tools/semantic_mcp_router.py`:

1. Encode tool descriptions with BGE-small.
2. Store vectors in FAISS.
3. Encode user query.
4. Retrieve top 3 tools.
5. Inject only selected tool schemas into the prompt.

Acceptance criteria:

- 40 registered tools become top 3 selected tools.
- Token count reduction is measured.
- Router benchmark writes `benchmarks/results/router_accuracy.json`.

## 9. Implement Reasoning-Token Governor

Implement `app/governor.py`:

```python
def cap(plan):
    cap = 4096
    if plan.tool_confidence_top1 > 0.85:
        cap = min(cap, 256)
    if plan.kv_pressure > 0.70:
        cap = min(cap, 512)
    if plan.slo_remaining_ms < 4000:
        cap = min(cap, int(256 + 4 * plan.tool_confidence_top1 * 1024))
    if plan.self_consistency_score > 0.90:
        cap = min(cap, 128)
    return cap
```

Inject this into the system prompt:

```text
You may reason for up to {cap} tokens before producing a tool call.
If your selected tool confidence is >= 0.85, commit immediately.
```

Acceptance criteria:

- Average thinking tokens are reduced.
- Accuracy drop is measured, not guessed.
- Results are saved to `benchmarks/results/governor.json`.

## 10. Implement Adaptive Quantization Router

Implement `app/aqr.py`:

```python
QUANT_BY_ROLE = {
    "reasoning": "Q5_K_M",
    "tool_call": "Q4_0",
    "summarization": "Q4_0",
    "code": "Q5_K_M",
    "classification": "Q4_0",
}
```

Use AQR to choose the preferred model endpoint. In the MVP, this can be a static policy. Add RL only after the static version works.

Acceptance criteria:

- Request metadata includes selected quant policy.
- Benchmark compares Q4 vs Q5 latency and quality.

## 11. Add Mem0 and OKF Memory

Implement `app/memory/okf_loader.py`:

- Read `okf/index.md`.
- Resolve relevant agent/tool/policy files.
- Load only needed Markdown into context.

Implement `app/memory/mem0_client.py`:

- `remember(agent_id, fact, metadata)`
- `recall(agent_id, query, limit)`
- fallback to local FAISS if Mem0 is unavailable.

Acceptance criteria:

- Agent can recall facts from previous requests.
- OKF context loading is progressive, not full-folder stuffing.
- Memory fallback works without external services.

## 12. Implement KV Persistence Before CXL/MTE

**Implemented:** Plane-2 KV Memory Runtime at `neuroswarm_arm/runtime/kv/` (see [`docs/kv-memory-runtime.md`](docs/kv-memory-runtime.md)).

Legacy `neuroswarm_arm/memory/kv_pager.py` is a compatibility wrapper over `KVRuntimeManager`.

MVP behavior (shipped):

1. Fixed-size blocks (default 256 tokens) with logical→physical tables.
2. Automatic tiering L1 RAM → L2 Compressed → L3 mmap/NVMe → L4 LMDB → L5 Redis under pressure (≥0.70).
3. Checkpoint / restore / resume with metadata separate from payloads.
4. Prefix cache, dedup, CoW, multi-agent sharing backends (no MTE).
5. Governor consumes real `pressure_snapshot()` (hit rate, tier, migration latency).

Do not make native CXL/MTE the first demo path. `CXLProvider` / `MTEProvider` are architecture stubs only.

Acceptance criteria:

- A long session survives process restart via `/kv/checkpoint` + `/kv/restore`.
- `python benchmarks/kv_run_all.py` emits reports under `work/benchmarks/`.
- README / docs honestly label NVMe/mmap as the Axion path and CXL/MTE as future backends.

## 13. Add HAOE Scheduler

Implement simple scheduler first in `app/router.py`:

- priority queue
- critical tasks routed to reserved core range
- background tasks routed separately
- NUMA hints passed to subprocess/server selection

Then add optional native SVE2 JSON parser in `native/json_sve2.c`.

Acceptance criteria:

- Multi-agent load test shows predictable core assignment.
- SVE2 parser is optional and does not block the main demo.

## 14. Integrate Arm Performix

Install Performix on the Arm host and save recipes under `benchmarks/recipes/`.

Required recipes:

```bash
apx recipe run system-characterization --output benchmarks/results/01-sys-char.json
apx recipe run code-hotspots --binary /usr/local/bin/llama-server --output benchmarks/results/02-baseline.svg
apx recipe run code-hotspots --binary /usr/local/bin/neuroswarm-router --output benchmarks/results/03-optimized.svg
apx recipe run cpu-microarch --binary /usr/local/bin/neuroswarm-router --output benchmarks/results/04-topdown.svg
apx recipe compare --baseline benchmarks/results/02-baseline.json --optimized benchmarks/results/03-optimized.json --output benchmarks/results/05-comparison.md
```

Implement `app/evolution/performix_client.py`:

- run recipe
- collect output path
- parse summary metrics
- expose latest hotspot list to dashboard

Acceptance criteria:

- At least one baseline and one optimized flame graph exist.
- Benchmark comparison is reproducible from `benchmarks/run_all.sh`.

## 15. Add AROP (Plane 5) — Autonomic Runtime Optimization Plane

Implement `neuroswarm_arm/evolution/` as AROP (not MAKS). NEXUS Layer 5 remains MAKS.

Pipeline (never Reflect → Deploy):

1. Observe (Performix / Runtime / Prom / OTel / PMU providers).
2. Normalize → Store (Mem0 evolution/ + OKF policy docs).
3. Analyze → Reflect (Rule / GEPA / Hybrid) → **PolicyDelta only**.
4. Materialize immutable `RuntimePolicy` candidates.
5. Offline evaluation + Replay.
6. Shadow execution.
7. Statistical validation + SafetyGate.
8. Canary deployment (sticky agent_id hash).
9. Monitor → promote or rollback.
10. Knowledge update + policy lineage.

MVP knobs (wired adapters):

- cascade confidence / accept threshold
- draft token count
- reasoning-token cap
- top-k tool count

Full knob catalog also covers HAOE threads/NUMA, MAKS eviction, Mem0 retention, etc. (dry-run adapters until backends expose setters).

```bash
pytest tests/runtime/evolution -q
python benchmarks/arop/run_benchmark.py
# HTTP
curl -X POST http://localhost:8000/arop/optimize
curl http://localhost:8000/arop/health
```

Acceptance criteria:

- AROP never silently deploys worse settings (SafetyGate + validation).
- Every change is a versioned policy with before/after knowledge record.
- CI passes with `NSA_AROP_PERFORMIX=0` (mocks).

Docs: `docs/arop/architecture.md`.

## 16. Build Dashboard

Expose Prometheus metrics:

- `neuroswarm_request_latency_ms`
- `neuroswarm_tokens_input_total`
- `neuroswarm_tokens_output_total`
- `neuroswarm_cost_usd_total`
- `neuroswarm_cascade_tier_total`
- `neuroswarm_tool_schema_tokens`
- `neuroswarm_thinking_tokens`
- `neuroswarm_kv_memory_bytes`
- `neuroswarm_performix_hotspot_percent`

Grafana panels:

1. Tokens/sec.
2. Cost per 1M tokens.
3. Cascade hit rate.
4. Tool schema token reduction.
5. Thinking tokens per query.
6. KV memory usage.
7. Performix hotspots.
8. Arm vs H100 cost comparison.

Acceptance criteria:

- Dashboard works from Helm or docker-compose.
- Screenshot is saved to `benchmarks/screenshots/cost-dashboard.png`.

## 17. Package with Docker and Helm

Docker:

```bash
docker buildx build --platform linux/arm64 -t neuroswarm-arm:latest -f Dockerfile.arm64 .
```

Helm chart must deploy:

- FastAPI gateway
- Tier 1 llama-server
- Tier 2 llama-server
- Tier 3 llama-server
- semantic router
- Mem0 or local memory fallback
- Prometheus
- Grafana
- PVC for models, OKF, and KV cache

Acceptance criteria:

- `helm lint helm/neuroswarm-arm` passes.
- Fresh install works.
- `docs/setup.md` has exact commands.

## 18. Implement Benchmarks

Create scripts:

```text
benchmarks/run_all.sh
benchmarks/baseline_llama.py
benchmarks/cascade_acceptance.py
benchmarks/router_accuracy.py
benchmarks/governor_tokens.py
benchmarks/economics.py
benchmarks/kv_survival.sh
```

Each benchmark must output JSON.

Required proof:

| Claim | Script |
|---|---|
| Cascade speedup | `cascade_acceptance.py` + Performix |
| Tool schema reduction | `router_accuracy.py` |
| Thinking-token reduction | `governor_tokens.py` |
| KV session survival | `kv_survival.sh` |
| Tokens per dollar | `economics.py` |
| Arm-specific optimization | Performix recipes |

Acceptance criteria:

- Every README claim links to one benchmark file.
- No headline metric exists without a reproducible script.

## 19. Final Implementation Order

Build in this exact order:

1. Repository scaffold.
2. Arm instance verification.
3. llama.cpp + KleidiAI build.
4. Model download and smoke tests.
5. Baseline llama-server benchmark.
6. Tier 1 / Tier 2 / Tier 3 cascade.
7. FastAPI gateway.
8. Semantic MCP router.
9. Reasoning governor.
10. Static AQR.
11. Prometheus metrics.
12. Performix baseline and optimized runs.
13. Grafana dashboard.
14. Mem0 / OKF memory.
15. KV survival with NVMe fallback.
16. HAOE scheduling.
17. Performix-driven tuning loop.
18. MCP server templates.
19. Docker ARM64 image.
20. Helm chart.
21. Reproduction docs.
22. Demo video and submission assets.

## 20. MVP Cut Line

If time is short, ship this:

1. llama.cpp + KleidiAI on Arm.
2. CPU-CPU cascade.
3. FastAPI gateway.
4. Semantic MCP top-3 router.
5. Reasoning-token governor.
6. Performix flame graphs.
7. Grafana cost dashboard.
8. Docker + Helm.
9. Two MCP templates.
10. Benchmark scripts.

Defer these if needed:

- native CXL
- MTE KV sharing
- PPO-based router
- full GEPA evolution
- all six MCP templates
- SVE2 native JSON parser

This MVP still proves the main problem statement: agentic AI cost is reduced by removing wasted tool schemas, wasted reasoning tokens, duplicated inference work, and unmeasured Arm performance bottlenecks.

## 21. Definition of Done

The implementation is complete when:

1. A fresh Arm instance can run the project from documented commands.
2. `/v1/chat/completions` returns a valid agent response.
3. The response uses only top-k relevant MCP tool schemas.
4. The cascade reports which tier served the request.
5. The governor reports the thinking-token cap.
6. Grafana shows live latency, token, cost, tier, and hotspot metrics.
7. Performix outputs exist for baseline and optimized runs.
8. `benchmarks/run_all.sh` produces JSON results.
9. Helm install works on a fresh cluster.
10. README claims match measured benchmark outputs.

