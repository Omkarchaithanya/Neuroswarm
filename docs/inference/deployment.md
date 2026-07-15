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
- `GGML_KLEIDIAI_SME` — unset=auto, `0`=off

## Kubernetes / Helm

Chart: `helm/neuroswarm-arm/`

Probes:
- liveness → `/health`
- readiness → `/ready` (model files + backend health)
- startup → allow KleidiAI image pull/build time

Graceful shutdown: gateway `shutdown` event calls `armora.shutdown()` → DIPA `LifecycleManager` drain → backend stop.

## Rolling updates

Update `NSA_LLAMA_IMAGE` / chart image tags. Tier pods restart independently; cascade degrades to remaining healthy tiers via RecoveryStack.
