# Evidence pack (judge-visible)

`benchmarks/results/` is gitignored. Capture scripts copy key artifacts here so the public repo shows receipts.

## Layout

| Path | Contents |
|---|---|
| `latest/` | health, ready, metrics, run_all, compose ps, Kleidi gate, chat, tools-route, lscpu |
| `performix/` | GA recipe JSON + **`OPTIMIZATIONS.md`** + flame PNG + COMPARISON.md |

**Judges — Performix first:** [`performix/OPTIMIZATIONS.md`](performix/OPTIMIZATIONS.md) (hotspots → what we optimized) · [`performix/screenshots/05-code-hotspots-flame.png`](performix/screenshots/05-code-hotspots-flame.png).

## Regenerate on Axion

```bash
bash scripts/deploy-kleidiai-tiers.sh
bash scripts/capture-evidence.sh
bash performix_capture.sh
COMPARE=1 bash performix_capture.sh
```

## Pass gates

1. `kleidiai-runtime-gate.txt` says PASS (no stock `ggml-org/llama.cpp`)
2. `prometheus-metrics.txt` non-empty metric lines
3. `run_all.json` not `"status":"skipped"`
4. Performix `*instruction_mix*.json` present

Placeholder files below are replaced when you run capture on the VM.
