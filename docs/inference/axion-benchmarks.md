# Axion Benchmark Methodology

NeuroSwarm Axion benchmarks measure **honest, reproducible** efficiency on C4A VM
(virtualized Arm Neoverse). They do not claim binary GGML KV injection into
llama.cpp unless the session-to-slot bridge is active.

## Workloads

| Script | Purpose |
|--------|---------|
| `benchmarks/slot_reuse.py` | Multi-turn sessions; compares turn-1 vs turn-2+ latency |
| `scripts/validate_kleidiai.py` | Benchmark-based KleidiAI gate (median tok/s vs `kleidiai_baselines.json`, 15% floor) |
| `benchmarks/axion_demo_suite.py` | Aggregates baseline + KleidiAI into a markdown table |
| `scripts/perf_collect.sh` | `perf stat` sidecar (no SPE on VM) |

## Slot reuse

llama-server must start with:

```text
--parallel 4 --slot-save-path /var/lib/ns/slots
```

NeuroSwarm `SlotRouter` sends `id_slot` + `cache_prompt: true`. MAKS stores
**session metadata** (tier, slot id, token stats) — not GGML KV tensors.

## C4A VM limits

- Arm SPE / Performix Memory Access recipe requires **C4A Metal** (not VM).
- Use Code Hotspots + `perf stat` on VM.
- Demo on **tier2** (3B) for visible KleidiAI matmul gains.

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `NSA_DIPA_OTEL` | `1` in compose | DIPA trace spans |
| `NSA_MAKS_COMPRESSION` | `zstd` | Set `q8` for Q8 blob codec |
| `NSA_MAKS_EVICTION` | `scored` | Set `s3fifo` for S3-FIFO policy |
| `TIER2_PARALLEL` | `4` | llama-server slots |

## Success criteria (demo)

1. Turn-2+ TTFT reduction vs turn-1 on same session (target ≥ 40%).
2. KleidiAI validation `ok: true` (benchmark median ≥ 15% above `no_kleidiai` baseline).
3. Cloud Trace shows `neuroswarm.kv.load` → `chat` with `slot.id`.
