# Performix dynamic Instruction Mix — stock vs KleidiAI

Generated: 2026-07-20T19:27:00Z (post dual-stack fix)

**Deploy path:** Docker Compose only on Axion (k3s/Helm torn down). Obs scrapes a single `{job="neuroswarm-gateway"}` target at `10.128.0.2:80`.

Captured **during live decode** via PID-scoped `apx` under continuous chat load (not system-wide idle).

| Capture | Artifact | Notes |
|---|---|---|
| KleidiAI (optimized) | `03-instruction_mix_dynamic_kleidi.json` | Pre-fix dynamic mix retained; see README contamination note |
| Stock llama.cpp (baseline) | `04-instruction_mix_dynamic_baseline.json` | Pre-fix baseline retained for SIMD comparison |
| Code hotspots (post-fix) | `01-code_hotspots.json` / `snapshot.json` | Top: `libggml-cpu` ~79% (not `default_idle_call`) |

## Symbols

Kleidi image rebuilt with `RelWithDebInfo` + frame pointers; `libggml-cpu.so` is **with debug_info, not stripped**. Arm Performix still labeled samples as `<Unknown code in libggml-cpu.so…>` for container mappings — see `SYMBOLS.md`.

## Method

1. Continuous `POST /v1/chat/completions` for the full recipe window
2. Attach `apx` to host-visible `llama-server` PID (`--pid`, never `--system-wide` for evidence)
3. Single Compose stack only

## Scrapes (obs Prometheus)

Verified: only `neuroswarm-gateway@10.128.0.2:80` and `prometheus@localhost:9090`. `axion-otel-exporter` and k8s NodePort scrapes removed. Charts: `docs/evidence/performix/screenshots/`.
