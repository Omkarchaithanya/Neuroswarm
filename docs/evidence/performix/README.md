# Performix evidence (Axion)

status: captured  
host: GCP Axion c4a-standard-8 (Neoverse-V2)

| Artifact | Status |
|---|---|
| `01-code_hotspots.json` | OK (`source=apx`) |
| `02-instruction_mix.json` | Legacy static mix (pre confirmed-Kleidi window) |
| `static_instruction_mix.csv` | Legacy — NEON 1.61%, SVE 0.34% |
| `03-instruction_mix_dynamic_kleidi.json` | OK — Kleidi `libggml-cpu` during live decode load (**NEON 3.41% + SVE 0.94%**) |
| `03-instruction_mix_dynamic_kleidi.csv` | Companion static CSV from run `7b12273c713a` |
| `04-instruction_mix_dynamic_baseline.json` | OK — stock `libggml-cpu-armv9.2_2` (**NEON 2.14% + SVE 1.19%**) |
| `04-instruction_mix_dynamic_baseline.csv` | Companion CSV from run `dcc868c81924` |
| `05-cpu_microarchitecture.json` | OK recipe export (system-wide under load; PMU rows may be empty on this host) |
| `06-memory_access.json` | OK recipe export (system-wide under load; SPE often empty on this host) |
| `COMPARISON.md` | Kleidi vs stock side-by-side |
| `snapshot.json` | OK Grafana/RMF (`source=apx`, hotspots present) |
| `00-recipe-list.txt` | OK live `apx recipe list` (7 recipes including `system_utilization`) |

## Honesty notes

- Prefer **03 vs 04** for judge-facing SIMD claims (live Kleidi tiers + stock baseline).
- `instruction_mix --param mode=dynamic` / PID attach returned **0 attributed samples** here (SPE empty / gator warnings). Captures use `mode=both` on the **deployed** `libggml-cpu` while decode load runs.
- Reproduce: `bash scripts/capture-performix-dynamic.sh` (or `_remote_performix_capture.sh` on Axion).

## Reproduce

```bash
sudo apt-get install -y python3-venv
bash scripts/deploy-kleidiai-tiers.sh
NSA_PERFORMIX_ALLOW_DEMO=0 bash performix_capture.sh
bash scripts/capture-performix-dynamic.sh
```
