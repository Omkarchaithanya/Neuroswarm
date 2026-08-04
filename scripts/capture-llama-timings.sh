#!/usr/bin/env bash
# Capture llama.cpp native timings (API timings JSON and/or llama-cli stderr).
# Usage: bash scripts/capture-llama-timings.sh
# Env: TIER=1|2|3 (default 3), BASE, MAX_TOKENS, MODE=api|cli|both (default api), PROMPT
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p work/profiling
if [[ ! -w work/profiling ]]; then
  if command -v sudo >/dev/null 2>&1; then
    sudo chown -R "$(id -u):$(id -g)" work/profiling 2>/dev/null || sudo chmod -R a+rwX work/profiling 2>/dev/null || true
  fi
fi

TIER="${TIER:-3}"
MODE="${MODE:-api}"
MAX_TOKENS="${MAX_TOKENS:-64}"
PROMPT="${PROMPT:-Say hello in one short sentence.}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SUMMARY="work/profiling/llama-timings-${STAMP}.json"
SUMMARY_LATEST="work/profiling/llama-timings-summary.json"

case "${TIER}" in
  1) DEFAULT_BASE="http://127.0.0.1:8081"; MODEL="/models/xLAM-2-1b-fc-r-Q4_0.gguf"; SERVICE="tier1" ;;
  2) DEFAULT_BASE="http://127.0.0.1:8082"; MODEL="/models/xLAM-2-3b-fc-r-Q4_0.gguf"; SERVICE="tier2" ;;
  3) DEFAULT_BASE="http://127.0.0.1:8083"; MODEL="/models/DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"; SERVICE="tier3" ;;
  *) echo "TIER must be 1, 2, or 3" >&2; exit 1 ;;
esac
BASE="${BASE:-$DEFAULT_BASE}"

echo "MODE=${MODE} TIER=${TIER} BASE=${BASE} MAX_TOKENS=${MAX_TOKENS}"

API_JSON=""
CLI_TXT=""
API_OK=0
CLI_OK=0

if [[ "${MODE}" == "api" || "${MODE}" == "both" ]]; then
  API_JSON="work/profiling/llama-timings-api-${STAMP}.json"
  BODY="$(PROMPT="${PROMPT}" MAX_TOKENS="${MAX_TOKENS}" python3 - <<'PY'
import json, os
print(json.dumps({
  "model": "default",
  "messages": [{"role": "user", "content": os.environ.get("PROMPT", "Say hello")}],
  "max_tokens": int(os.environ.get("MAX_TOKENS", "64")),
  "temperature": 0.2,
}))
PY
)"
  set +e
  curl -sS -m 180 -X POST "${BASE}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "${BODY}" \
    >"${API_JSON}"
  API_RC=$?
  set -e
  if [[ ${API_RC} -eq 0 ]] && python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert isinstance(d.get('timings'), dict)" "${API_JSON}" 2>/dev/null; then
    API_OK=1
    echo "API timings OK → ${API_JSON}"
  else
    echo "API timings missing or request failed (rc=${API_RC})" >&2
    head -c 400 "${API_JSON}" 2>/dev/null || true
    echo
  fi
fi

if [[ "${MODE}" == "cli" || "${MODE}" == "both" ]]; then
  CLI_TXT="work/profiling/llama-timings-cli-${STAMP}.txt"
  set +e
  docker compose run --rm --no-deps --entrypoint llama-cli "${SERVICE}" \
    -m "${MODEL}" \
    -n "${MAX_TOKENS}" \
    -t "$(nproc 2>/dev/null || echo 4)" \
    -ngl 0 \
    -p "${PROMPT}" \
    >"${CLI_TXT}" 2>&1
  CLI_RC=$?
  set -e
  if [[ ${CLI_RC} -eq 0 ]] && grep -q 'llama_print_timings' "${CLI_TXT}" 2>/dev/null; then
    CLI_OK=1
    echo "CLI timings OK → ${CLI_TXT}"
  elif grep -qiE 'executable file not found|no such file|unknown.*llama-cli' "${CLI_TXT}" 2>/dev/null; then
    echo "llama-cli unavailable in image" >&2
    CLI_RC=127
  else
    echo "llama-cli finished without llama_print_timings (rc=${CLI_RC})" >&2
  fi
fi

export PROMPT MAX_TOKENS
python3 - "$SUMMARY" "$SUMMARY_LATEST" "$TIER" "$BASE" "$MODEL" "$MODE" "$API_JSON" "$CLI_TXT" "$API_OK" "$CLI_OK" "$MAX_TOKENS" "$PROMPT" <<'PY'
import json, re, sys
from pathlib import Path

(
    summary, latest, tier, base, model, mode,
    api_json, cli_txt, api_ok, cli_ok, max_tokens, prompt,
) = sys.argv[1:13]
api_ok = int(api_ok)
cli_ok = int(cli_ok)

def parse_api(path: str) -> dict:
    if not path or not Path(path).exists():
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    t = raw.get("timings") if isinstance(raw, dict) else None
    if not isinstance(t, dict):
        return {"error": "timings_missing", "raw_keys": list(raw.keys()) if isinstance(raw, dict) else []}
    out = {
        "source": "llama_server_timings",
        "prompt_ms": float(t.get("prompt_ms") or 0.0),
        "predicted_ms": float(t.get("predicted_ms") or 0.0),
        "prompt_n": float(t.get("prompt_n") or 0.0),
        "predicted_n": float(t.get("predicted_n") or 0.0),
        "prompt_per_second": float(t.get("prompt_per_second") or 0.0),
        "predicted_per_second": float(t.get("predicted_per_second") or 0.0),
        "prompt_per_token_ms": float(t.get("prompt_per_token_ms") or 0.0),
        "predicted_per_token_ms": float(t.get("predicted_per_token_ms") or 0.0),
        "timings": t,
    }
    # Refuse "success" labeling when the server returned an empty timings object.
    if out["predicted_per_second"] <= 0 and out["prompt_per_second"] <= 0:
        return {
            "source": "llama_server_timings_unavailable",
            "error": "timings_all_zero",
            "timings": t,
        }
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    out["usage"] = usage
    return out

def parse_cli(path: str) -> dict:
    if not path or not Path(path).exists():
        return {"source": "llama_cli_unavailable", "error": "no_output"}
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if "llama_print_timings" not in text:
        if re.search(r"executable file not found|no such file", text, re.I):
            return {"source": "llama_cli_unavailable", "error": "binary_missing"}
        return {"source": "llama_cli_unavailable", "error": "no_timings_lines"}
    def grab(label: str) -> float | None:
        m = re.search(rf"llama_print_timings:\s+{label}\s*=\s*([\d.]+)\s*ms", text)
        return float(m.group(1)) if m else None
    load_ms = grab("load time")
    sample_ms = grab("sample time")
    prompt_ms = grab("prompt eval time")
    eval_ms = grab("eval time")
    total_ms = grab("total time")
    # tokens / runs from lines like: prompt eval time = 341.20 ms / 12 tokens
    prompt_n = None
    predicted_n = None
    m = re.search(r"prompt eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens", text)
    if m:
        prompt_ms = float(m.group(1))
        prompt_n = float(m.group(2))
    m = re.search(r"eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*runs", text)
    if m:
        eval_ms = float(m.group(1))
        predicted_n = float(m.group(2))
    prompt_per_s = (prompt_n / (prompt_ms / 1000.0)) if prompt_ms and prompt_n else 0.0
    predicted_per_s = (predicted_n / (eval_ms / 1000.0)) if eval_ms and predicted_n else 0.0
    return {
        "source": "llama_cli_timings",
        "load_ms": load_ms,
        "sample_ms": sample_ms,
        "prompt_ms": prompt_ms or 0.0,
        "predicted_ms": eval_ms or 0.0,
        "total_ms": total_ms,
        "prompt_n": prompt_n or 0.0,
        "predicted_n": predicted_n or 0.0,
        "prompt_per_second": prompt_per_s,
        "predicted_per_second": predicted_per_s,
    }

payload: dict = {
    "tier": int(tier),
    "base": base,
    "model": model,
    "mode": mode,
    "max_tokens": int(max_tokens),
    "prompt": prompt,
    "api": None,
    "cli": None,
}
primary = None
if api_ok:
    payload["api"] = parse_api(api_json)
    primary = payload["api"]
elif mode in ("api", "both") and api_json:
    payload["api"] = parse_api(api_json) or {"source": "llama_server_timings_unavailable", "error": "request_or_parse_failed"}

if cli_ok:
    payload["cli"] = parse_cli(cli_txt)
    if primary is None:
        primary = payload["cli"]
elif mode in ("cli", "both"):
    payload["cli"] = parse_cli(cli_txt) if cli_txt else {"source": "llama_cli_unavailable", "error": "not_run"}

if primary and primary.get("source") in ("llama_server_timings", "llama_cli_timings"):
    # Extra honesty: live sources must show non-zero throughput.
    pred = float(primary.get("predicted_per_second") or 0.0)
    prompt = float(primary.get("prompt_per_second") or 0.0)
    if pred <= 0 and prompt <= 0:
        payload["source"] = "llama_timings_unavailable"
        payload["error"] = "zero_throughput"
    else:
        payload["source"] = primary["source"]
        for k in (
            "prompt_ms", "predicted_ms", "prompt_n", "predicted_n",
            "prompt_per_second", "predicted_per_second",
        ):
            if k in primary:
                payload[k] = primary[k]
else:
    payload["source"] = "llama_timings_unavailable"
    payload["error"] = "no_usable_timings"

Path(summary).write_text(json.dumps(payload, indent=2), encoding="utf-8")
Path(latest).write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(
    f"Wrote {summary} source={payload.get('source')} "
    f"predicted_tok_s={payload.get('predicted_per_second')} "
    f"prompt_tok_s={payload.get('prompt_per_second')}"
)
PY

echo "Done. Summary: ${SUMMARY} (also ${SUMMARY_LATEST})"
