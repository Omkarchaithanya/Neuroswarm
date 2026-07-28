# Deployment Guide — Inference

## Docker Compose

```bash
# Build KleidiAI llama-server + gateway
docker compose build tier1 gateway
docker compose up -d
curl -s localhost:8000/ready
```

Env:
- `NSA_REQUIRE_KLEIDIAI=1` — fail readiness if `CPU_KLEIDIAI` missing from logs
- `NSA_DIPA_KLEIDIAI=1` — mark capabilities.kleidiai
- `GGML_KLEIDIAI_SME` — unset=auto, `0`=off (**Axion C4A has no SME2** — SVE2+I8MM only; see `GET /build-info`)
- `NSA_AROP_CANARY_PCT` — AROP canary traffic percent (default **5**)
- `NSA_RTG_PPO` — optional offline PPO scaffold (`0` default; live path is bandit/heuristics)
- `NSA_DIPA_OTEL=1` — enable DIPA OpenTelemetry spans (default in compose)
- `NSA_DIPA_OTEL_ENDPOINT` — OTLP HTTP endpoint for trace export
- `TIER*_PARALLEL=4` — llama-server slot count per tier
- `NSA_MAKS_COMPRESSION=q8` — optional Q8 blob compression in MAKS
- `NSA_MAKS_EVICTION=s3fifo` — optional S3-FIFO eviction policy

### llama-server slot persistence

Each tier mounts a writable volume at `/var/lib/ns/slots` and starts with:

```text
--parallel 4 --slot-save-path /var/lib/ns/slots
```

NeuroSwarm `SlotRouter` binds `session_id` → `id_slot` and uses `cache_prompt: true`
for multi-turn reuse. Validate KleidiAI:

```bash
python scripts/validate_kleidiai.py --url http://127.0.0.1:8080
python benchmarks/slot_reuse.py --url http://127.0.0.1:8080
```

## Kubernetes / Helm

Chart: `helm/neuroswarm-arm/`

Probes:
- liveness → `/health`
- readiness → `/ready` (model files + backend health)
- startup → allow KleidiAI image pull/build time

Graceful shutdown: gateway `shutdown` event calls `armora.shutdown()` → DIPA `LifecycleManager` drain → backend stop.

## Rolling updates

Update `NSA_LLAMA_IMAGE` / chart image tags. Tier pods restart independently; cascade degrades to remaining healthy tiers via RecoveryStack.
