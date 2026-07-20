# Demo-path TODO / NotImplementedError triage

Date: 2026-07-18  
Scope: gateway → router → DIPA → cascade → metrics only.

## Method

```bash
rg -n "NotImplementedError|TODO|FIXME" neuroswarm_arm --glob "*.py"
```

## Buckets

| Bucket | Finding | Action |
|---|---|---|
| **ABC / interface stubs** | Vast majority (~240) in `runtime/*/interfaces/*.py`, `haoe/interfaces`, `maks/interfaces`, evolution interface packages | **Leave** — normal Protocol/ABC pattern; concrete impls exist beside them |
| **Demo path** | `main.py`, `evolution/api/gateway.py`, `runtime/router/` (non-interfaces), `runtime/dipa/execution/`, `metrics/` | **No blocking NotImplementedError** found on request path |
| **Future / optional** | CXL native paths, MTE hard binds, multi-NUMA affinity when nodes&lt;2 | Already degrade via topology HAL (Option A) |

## Conclusion

Do **not** burn calendar clearing ABC stubs. Critical path is evidence (KleidiAI image, metrics, run_all, Performix), not finishing every interface file.

## Re-check before submit

```bash
# Smoke the live path
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"ping"}],"max_tokens":16}'
bash scripts/capture-evidence.sh
```
