# ADR 0003: Connectors, Not Ownership

## Status

Accepted

## Context

AQR (quant), AWPP (warm), MAKS (KV sharing) are peer layers. Embedding their policy engines inside DIPA creates circular ownership.

## Decision

DIPA exposes ports (`IQuantConnector`, `IWarmConnector`, `IKVCacheConnector`) and only asks. Peer layers own policy/storage.

## Consequences

- Quant strings never hardcoded in routers
- Warm prediction can evolve to PPO without DIPA refactor
- KV sharing uses existing runtime/kv sharing backends today
