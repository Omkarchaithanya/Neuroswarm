# Native llama.cpp profiling

Llama.cpp ships its own receipts for prefill/decode speed. NeuroSwarm captures them
alongside host profilers (perf / eBPF / Arm Performix).

| Layer | What | When to use |
|-------|------|-------------|
| **1. Completion timings** | JSON `timings` on chat responses, or `llama_print_timings` from `llama-cli` | Per-request prefill vs decode tok/s |
| **2. llama-bench** | Automated `-t` / `-p` / `-n` matrix | Compare thread/context configs |
| **3. llama-server `/metrics`** | Prometheus on tiers `:8081–8083` | Live slots, KV, cumulative tokens |
| **4. HW profilers** | Linux perf, bpftrace, Performix | Kernel/operator / PMU hotspots |

ProfInfer / Streamline / nsys are out of band — see [linux-perf-ebpf.md](linux-perf-ebpf.md) for the open-source host path.

## 1) End-of-run / completion timings

### API (default — live stack)

```bash
TIER=3 MAX_TOKENS=64 bash scripts/capture-llama-timings.sh
# or: BASE=http://127.0.0.1:8000 MODE=api …
```

Writes `work/profiling/llama-timings-*.json` with:

- `prompt_ms` / `prompt_per_second` — **prefill**
- `predicted_ms` / `predicted_per_second` — **decode**
- `source=llama_server_timings`

### CLI (`llama_print_timings`)

```bash
MODE=cli TIER=2 bash scripts/capture-llama-timings.sh
# or MODE=both
```

Parses stderr lines like `llama_print_timings: prompt eval time = …` / `eval time = …`.
If the Kleidi image lacks `llama-cli`, the JSON records honest `llama_cli_unavailable`.

## 2) llama-bench sweeps

```bash
TIER=2 THREADS=2,4,8 PROMPTS=128,512 NGEN=64,128 bash scripts/run-llama-bench-sweep.sh
```

Uses `docker compose run --entrypoint llama-bench tierN …`. Output:

- `work/profiling/llama-bench-tierN-*.json`
- matching `.md` table
- `work/profiling/llama-bench-summary.json`

## 3) Native server `/metrics`

Tiers already start with `--metrics`. Obs Prometheus scrapes:

| Target | Tier |
|--------|------|
| `10.128.0.2:8081` | tier1 |
| `10.128.0.2:8082` | tier2 |
| `10.128.0.2:8083` | tier3 |

Job name: `llama-server-tiers`. Grafana dashboard: **NeuroSwarm Llama Server Metrics**
(`neuroswarm-llama-server`).

Quick check on Axion:

```bash
curl -sS http://127.0.0.1:8083/metrics | head -40
```

## 4) Gateway passthrough

When llama-server returns `timings`, the DIPA llama.cpp backend copies them into
`GenerateResult.metrics` (`llama_prompt_ms`, `llama_predicted_per_second`, …).
`DIPAMetrics.record_inference` prefers those values for `dipa_decode_tps` /
`dipa_prefill_tps` / `nexus_tokens_per_second` instead of client wall-clock estimates.

## How to read prefill vs decode

| Stage | API field | CLI line | Meaning |
|-------|-----------|----------|---------|
| Prefill | `prompt_*` | `prompt eval time` | Process the input prompt |
| Decode | `predicted_*` | `eval time` | Generate output tokens one-by-one |

## vs host profilers

| | Native llama | Linux perf / eBPF | Performix |
|--|--------------|-------------------|-----------|
| Tok/s receipt | Yes | No | Indirect |
| Kernel / NEON hotspots | No | Yes | Yes (GUI/recipes) |
| Live Prometheus | Tier `/metrics` | `profile_*` | `nexus_performix_*` |

Use native timings for **throughput honesty**; use perf/eBPF/Performix for **where CPU time went**.

## Honesty rules (no demo data)

- Capture scripts never write `source=demo` / `synthetic`.
- Timings success requires non-zero `predicted_per_second` or `prompt_per_second` from the server (or CLI parse). Empty timings → `*_unavailable`.
- Gateway only copies `raw["timings"]` when present — it does **not** invent tok/s defaults.
- Linux perf may use `event_mode=software` when HW PMU is absent; IPC stays `0` (not fabricated).
- Performix remains gated by `NSA_PERFORMIX_ALLOW_DEMO=0` on Axion.

Re-check on the VM:

```bash
bash scripts/verify-profiling-honesty.sh
```
