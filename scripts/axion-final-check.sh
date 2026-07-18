#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sed -i 's/\r$//' scripts/*.py scripts/*.sh 2>/dev/null || true

echo "==> logprobs probe via gateway→tier2"
docker compose exec -T gateway python - <<'PY'
import json, urllib.request
url = "http://tier2:8080/v1/chat/completions"
for name, extra in [("lp", {"logprobs": True, "top_logprobs": 3}), ("np", {"n_probs": 3})]:
    body = json.dumps({
        "model": "x",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 3,
        "temperature": 0,
        **extra,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
            c = (d.get("choices") or [{}])[0]
            print(name, "ok", list(c.keys()), bool(c.get("logprobs") or c.get("completion_probabilities")))
    except Exception as e:
        print(name, "fail", e)
PY

echo "==> mem0 remember/recall"
docker compose exec -T gateway python - <<'PY'
import json
from neuroswarm_arm.runtime.memory import build_memory_runtime
m = build_memory_runtime()
h = m.health()
print("provider", getattr(h, "provider", None))
m.remember_fact("User favorite color is teal-axion-smoke.", owner="smoke-final")
hits = list(m.recall("smoke-final", "favorite color", limit=5) or [])
print(json.dumps({"recall_hits": len(hits), "sample": [str(x)[:80] for x in hits[:2]]}))
PY

echo "==> ascr"
python3 scripts/ascr-logits-smoke.py --base http://127.0.0.1:8000 --n 2 || true

echo "==> performix refresh"
set +e
NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 bash scripts/refresh-performix-snapshot.sh
echo "refresh_rc=$?"
set -e
python3 -c "import json;from pathlib import Path;p=Path('work/performix/snapshot.json');print('source', json.loads(p.read_text()).get('source') if p.is_file() else 'missing')"
