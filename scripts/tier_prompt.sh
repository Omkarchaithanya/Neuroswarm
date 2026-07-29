#!/usr/bin/env bash
# Send one prompt to a tier directly (bypass smart cascade). Run on VM.
# Usage:
#   bash scripts/tier_prompt.sh 1 "What is 2+2?"
#   bash scripts/tier_prompt.sh 2 "Explain TCP vs UDP" 256
#   bash scripts/tier_prompt.sh 3 "Solve step by step: train collision problem" 400
set -euo pipefail

TIER="${1:-}"
PROMPT="${2:-What is 2+2? Answer briefly.}"
MAX_TOKENS="${3:-256}"
TIMEOUT_SEC="${4:-600}"

if [[ -z "$TIER" || ! "$TIER" =~ ^[123]$ ]]; then
  echo "Usage: $0 <tier:1|2|3> [prompt] [max_tokens] [timeout_sec]" >&2
  exit 1
fi

declare -A PORTS=([1]=8081 [2]=8082 [3]=8083)
declare -A MODELS=([1]=tier1 [2]=tier2 [3]=tier3)
declare -A NAMES=(
  [1]="Qwen2.5-0.5B (fast / basic)"
  [2]="Qwen2.5-3B (medium)"
  [3]="DeepSeek-R1-7B (advanced)"
)

PORT="${PORTS[$TIER]}"
URL="http://127.0.0.1:${PORT}/v1/chat/completions"

if ! curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 \
  && ! curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
  echo "ERROR: tier${TIER} not reachable on port ${PORT}." >&2
  echo "Nothing listening — tier containers are not running OR you are on k8s/Helm mode." >&2
  echo "" >&2
  echo "Run the automated fix:" >&2
  echo "  bash scripts/tier_ports_fix.sh" >&2
  echo "" >&2
  echo "Manual checks:" >&2
  echo "  docker compose ps" >&2
  echo "  kubectl get pods 2>/dev/null    # if k8s: ports 8081-8083 do NOT exist" >&2
  echo "  ss -ltnp | grep -E '8081|8082|8083|30080'" >&2
  echo "" >&2
  echo "k8s mode: use gateway instead:" >&2
  echo "  bash scripts/smart_cascade_prompt.sh -m 512 \"your prompt\"" >&2
  exit 1
fi

payload="$(python3 - <<'PY' "$TIER" "$PROMPT" "$MAX_TOKENS" "${MODELS[$TIER]}"
import json, sys
tier, prompt, max_tokens, model = sys.argv[1:5]
body = {
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": int(max_tokens),
    "stream": False,
}
if tier == "3":
    body["chat_template_kwargs"] = {"enable_thinking": False}
    body["messages"] = [
        {"role": "system", "content": "Answer directly and concisely. Do not use chain-of-thought."},
        {"role": "user", "content": prompt},
    ]
print(json.dumps(body))
PY
)"

echo "Tier $TIER - ${NAMES[$TIER]} - $URL"
echo "Prompt: $PROMPT"
echo ""

start_ms="$(python3 -c 'import time; print(int(time.time()*1000))')"
resp="$(curl -sS --max-time "$TIMEOUT_SEC" -H "Content-Type: application/json" -d "$payload" "$URL")"
end_ms="$(python3 -c 'import time; print(int(time.time()*1000))')"

python3 - <<'PY' "$resp" "$start_ms" "$end_ms" "$TIER"
import json, re, sys
data = json.loads(sys.argv[1])
start_ms, end_ms, tier = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
msg = ((data.get("choices") or [{}])[0]).get("message") or {}
text = (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "").strip()
text = re.sub(r"(?s)^[\s\S]*?(?:|</think>)\s*", "", text).strip()
usage = data.get("usage") or {}
finish = ((data.get("choices") or [{}])[0]).get("finish_reason") or "unknown"
pt, ct = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
lat = max(0.001, (end_ms - start_ms) / 1000.0)
print("--- Metrics ---")
print(f"Tier               : {tier}")
print(f"Latency (wall)     : {lat:.3f}s")
print(f"Prompt tokens      : {pt}")
print(f"Completion tokens  : {ct}")
print(f"Completion tok/s   : {(ct/lat):.3f}")
print(f"Finish reason      : {finish}")
if finish == "length":
    print("NOTE: Response truncated — increase max_tokens (3rd arg).")
print()
print("--- Response ---")
print(text)
PY
