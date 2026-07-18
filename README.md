# NeuroSwarm-Arm

NeuroSwarm-Arm is an Arm-native agent runtime for the ARM Cloud AI Optimization Challenge. The MVP runs on a single GCP Axion VM and combines:

- llama.cpp CPU inference on Arm64
- three-tier CPU cascade routing
- semantic MCP tool selection (TurboVec ANN + hybrid rerank; see [`neuroswarm_arm/runtime/router/docs/`](neuroswarm_arm/runtime/router/docs/))
- reasoning-token governance
- adaptive quantization policy metadata
- HAOE Layer-1 runtime kernel (task graphs, work stealing, affinity HAL, telemetry)
- DIPA Layer-2 inference runtime kernel (planner, **ASCR** cascade, backends, streaming, recovery)
- Prometheus metrics for latency, tier usage, tool schemas, and token caps

## Semantic MCP Tool Router

Replaces naïve injection of all MCP tool schemas with Top-K semantic routing:

`BGE-small → TurboVec → hybrid retrieval → rerank → Top-K schemas → DIPA`

```bash
pytest tests/runtime/router -q
python benchmarks/router_full.py
```

## HAOE (Layer 1)

Chat requests execute as HAOE task graphs (route → KV session → DIPA → checkpoint → response). HAOE coordinates inference; it does not run models. Topology/affinity providers degrade safely on Axion (no NUMA/MTE/CXL assumptions). See [`docs/haoe/architecture.md`](docs/haoe/architecture.md) and ADRs under `docs/haoe/adr/`.

```bash
pytest tests/runtime/haoe -q
```

## DIPA (Layer 2)

DIPA is the Inference Runtime Kernel. Agents never call llama.cpp / vLLM / ExecuTorch / LiteRT directly — everything flows through DIPA (execution planner → model/backend/quant routers → **ASCR** → prefill/decode → streaming → metrics). AQR / AWPP / MAKS are connectors only. See [`docs/dipa/architecture.md`](docs/dipa/architecture.md) and [`docs/armcascade/`](docs/armcascade/README.md).

```bash
pytest tests/runtime/dipa -q
```

## Local Axion MVP

```bash
uv sync --all-groups
cp .env.example .env   # Linux/macOS; on Windows: Copy-Item .env.example .env
docker compose --compatibility up --build -d
```

The gateway listens on `http://VM_EXTERNAL_IP:8000`.

Health check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

Chat request:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Plan a cost-optimized ARM inference demo."}],"max_tokens":256}'
```

Detailed from-scratch setup is in `docs/gcp-axion-setup.md`.

Deploy scripts:

- `scripts/sync-vm.ps1` — push repo to Axion
- `scripts/deploy-vm.ps1` — sync + bootstrap
- `scripts/deploy-k8s.sh` — Helm one-command
- `scripts/bootstrap-gcp.ps1` / `scripts/bootstrap-vm.sh`

Initial dev target: `c4a-standard-8` with `hyperdisk-balanced`.
