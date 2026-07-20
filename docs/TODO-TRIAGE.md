# TODO / NotImplementedError triage (demo-path only)

Generated for Close Evidence Loop. Do **not** try to finish all ~240 ABC stubs.

## Verdict

| Bucket | Count / location | Action |
|---|---|---|
| **Demo path** (gateway → router → DIPA exec → metrics) | `main.py`, `evolution/api`, `runtime/router` (non-interface), `metrics` — **no blocking `NotImplementedError`** | Keep green; only fix regressions |
| **ABC / interface stubs** | `runtime/haoe/interfaces` (~36), `runtime/dipa/interfaces/*`, `runtime/maks/interfaces`, `evolution/interfaces` | **Future work** — concrete impls already live beside them |
| **Optional planes** | armcascade proposal stubs, awpp extras | Out of demo path |

## Demo-path smoke (must stay green)

```bash
uv run pytest tests/runtime/router tests/runtime/dipa tests/runtime/haoe -q --maxfail=5
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
bash scripts/capture-evidence.sh
```

## Do not fix this week

Abstract `raise NotImplementedError` inside `*/interfaces/*.py` used as Protocol/ABC markers — expected.

## Measured benches (P1)

Run on KleidiAI tiers; drop JSON into `docs/evidence/latest/`:

```bash
uv run python benchmarks/cascade_acceptance.py
uv run python benchmarks/router_accuracy.py
uv run python benchmarks/governor_tokens.py
uv run python benchmarks/run_all.py --out docs/evidence/latest/run_all.json
```

Then replace aspirational rows in `05-BENCHMARK-PLAN.md` with measured values.
