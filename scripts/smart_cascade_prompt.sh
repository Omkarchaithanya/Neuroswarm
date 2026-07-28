#!/usr/bin/env bash
# Smart cascade prompt against gateway (run on VM or Linux host).
# Usage:
#   bash scripts/smart_cascade_prompt.sh "explain me about vLLM in an advanced way"
#   bash scripts/smart_cascade_prompt.sh -p "What is 2+2?" -m 128
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8000/v1/chat/completions}"
PROMPT=""
PROMPT_FILE=""
MAX_TOKENS=128
TIMEOUT_SEC=600

usage() {
  echo "Usage: $0 [-p PROMPT | -f PROMPT_FILE] [-m MAX_TOKENS] [-u GATEWAY_URL] [-t TIMEOUT_SEC]" >&2
  echo "   or: $0 \"your prompt here\"" >&2
  exit 1
}

while getopts ":p:f:m:u:t:h" opt; do
  case "$opt" in
    p) PROMPT="$OPTARG" ;;
    f) PROMPT_FILE="$OPTARG" ;;
    m) MAX_TOKENS="$OPTARG" ;;
    u) GATEWAY_URL="$OPTARG" ;;
    t) TIMEOUT_SEC="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1)) || true
if [[ -z "$PROMPT" && -n "$PROMPT_FILE" && -f "$PROMPT_FILE" ]]; then
  PROMPT="$(tr -d '\r' < "$PROMPT_FILE")"
fi
if [[ -z "$PROMPT" && $# -gt 0 ]]; then
  PROMPT="$1"
fi
if [[ -z "$PROMPT" ]]; then
  usage
fi

payload="$(python3 - <<'PY' "$PROMPT" "$MAX_TOKENS"
import json, sys
print(json.dumps({
    "model": "cascade",
    "messages": [{"role": "user", "content": sys.argv[1]}],
    "max_tokens": int(sys.argv[2]),
    "stream": False,
}))
PY
)"

echo "Smart cascade - $GATEWAY_URL"
echo "Prompt: $PROMPT"
echo ""

start_ms="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"

if ! resp="$(curl -sS --max-time "$TIMEOUT_SEC" \
  -H "Content-Type: application/json" \
  -d "$payload" \
  "$GATEWAY_URL")"; then
  echo "ERROR: gateway request failed" >&2
  exit 1
fi

end_ms="$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)"

python3 - <<'PY' "$resp" "$start_ms" "$end_ms"
import json, re, sys

raw = sys.argv[1]
start_ms = int(sys.argv[2])
end_ms = int(sys.argv[3])
data = json.loads(raw)

choices = data.get("choices") or []
msg = (choices[0].get("message") if choices else {}) or {}
text = (msg.get("content") or "").strip()
if not text:
    text = (msg.get("reasoning_content") or "").strip()
text = re.sub(r"(?s)^[\s\S]*?(?:|</think>)\s*", "", text).strip()

usage = data.get("usage") or {}
pt = int(usage.get("prompt_tokens") or 0)
ct = int(usage.get("completion_tokens") or 0)
lat = max(0.001, (end_ms - start_ms) / 1000.0)
tps = ct / lat if lat > 0 else 0.0

metrics = data.get("metrics") or {}
tier_used = data.get("tier_used") or metrics.get("tier_used")
start_tier = metrics.get("cascade_start_tier")
hardness_band = metrics.get("hardness_band")
hardness_complexity = metrics.get("hardness_complexity")

print("--- Routing ---")
if hardness_band:
    print(f"Hardness band       : {hardness_band}")
if start_tier is not None:
    print(f"Cascade start tier  : {int(float(start_tier))}")
if tier_used is not None:
    print(f"Tier used (final)   : {int(float(tier_used))}")
if hardness_complexity is not None:
    print(f"Hardness complexity : {hardness_complexity}")

print()
print("--- Metrics ---")
print(f"Latency (wall)     : {lat:.3f}s")
print(f"Prompt tokens      : {pt}")
print(f"Completion tokens  : {ct}")
print(f"Completion tok/s   : {tps:.3f}")
print()
print("--- Response ---")
print(text)
PY
