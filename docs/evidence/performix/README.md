# Performix evidence (Axion)

status: captured  
host: GCP Axion c4a-standard-8 (Neoverse-V2)

| Artifact | Status |
|---|---|
| `01-code_hotspots.json` | OK (`source=apx`) |
| `02-instruction_mix.json` | OK (static Instruction Mix; needs `python3-venv` + `--workload`) |
| `static_instruction_mix.csv` | OK — NEON **1.61%**, SVE **0.34%** |
| `snapshot.json` | OK Grafana/RMF (`source=apx`, hotspots present) |
| `00-recipe-list.txt` | OK live `apx recipe list` |

## Reproduce

```bash
sudo apt-get install -y python3-venv
bash scripts/deploy-kleidiai-tiers.sh
NSA_PERFORMIX_ALLOW_DEMO=0 bash performix_capture.sh
# instruction_mix cannot use --system-wide; capture extracts Kleidi binary for --workload
```
