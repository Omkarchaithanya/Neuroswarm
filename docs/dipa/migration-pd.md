# Migration Guide: Fused Generate → PD Soft Mode

## Default (no change)

```bash
# or unset
export NSA_DIPA_PD_MODE=off
```

Existing cascade + llama.cpp fused `generate()` path unchanged.

## Enable soft PD (Axion recommended)

```bash
export NSA_DIPA_PD_MODE=soft
export NSA_DIPA_PREFILL_BACKEND=sglang
export NSA_DIPA_DECODE_BACKEND=llama_cpp
export NSA_DIPA_SGLANG_URL=http://127.0.0.1:30000
export NSA_DIPA_CHUNK_SIZE=2048
```

Docker Compose:

```bash
docker compose --profile pd up -d
```

Behavior:

1. Long prompts chunked by `ChunkPlanner`
2. Prefill via SGLang (`PrefillManager`)
3. Handoff via `KVTransferManager` mode `recompute`
4. Decode via llama.cpp (`DecodeManager`)
5. Metrics expose `dipa_kv_transfer_mode=recompute` and `dipa_recompute_tokens`

## Native same-engine PD (GPU/IB when available)

```bash
export NSA_DIPA_PD_MODE=native
export NSA_DIPA_SGLANG_ROUTER_URL=http://127.0.0.1:8000
```

Requires SGLang prefill + decode workers + router. Mooncake/NIXL must be `AVAILABLE`. On Axion without IB, stay on `soft`.

## Rollback

```bash
export NSA_DIPA_PD_MODE=off
```

Or stop `sglang-prefill` — DIPA falls back to fused llama.cpp when prefill health fails.

## Compatibility

| Consumer | Change required |
|----------|-----------------|
| ARMORA | None (streaming improved) |
| HAOE | None |
| AQR / AWPP / MAKS / RTG | None |
| Clients of `/v1/chat/completions` | None |
