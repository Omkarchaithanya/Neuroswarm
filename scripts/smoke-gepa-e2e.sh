#!/usr/bin/env bash
# GEPA HTTP e2e: optimize → approve → deploy → chat loads active prompt.
# Requires gateway with NSA_AROP_GEPA_LM=http://tier2:8080/v1 (PRODUCT_DEMO).
# Usage: bash scripts/smoke-gepa-e2e.sh [BASE_URL]
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REQUIRE_HTTP_TEACHER="${REQUIRE_HTTP_TEACHER:-1}"

echo "==> GEPA optimize"
OPT="$(curl -fsS "${BASE}/arop/optimize" -H 'Content-Type: application/json' -d '{"force":true}')"
echo "$OPT" | head -c 600
echo
CID="$(echo "$OPT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('gepa_candidate_id') or d.get('candidate_id') or '')" 2>/dev/null || true)"
if [[ -z "$CID" ]]; then
  # Fall back to pending list
  PENDING="$(curl -fsS "${BASE}/arop/gepa/pending")"
  CID="$(echo "$PENDING" | python3 -c "import sys,json; d=json.load(sys.stdin); p=d.get('pending') or []; print(p[0]['id'] if p else '')" 2>/dev/null || true)"
fi
if [[ -z "$CID" ]]; then
  echo "FAIL: no gepa_candidate_id from optimize/pending" >&2
  exit 1
fi
echo "candidate_id=$CID"

echo "==> GEPA approve"
curl -fsS "${BASE}/arop/gepa/approve" -H 'Content-Type: application/json' \
  -d "{\"candidate_id\":\"${CID}\",\"reviewer\":\"smoke\",\"reason\":\"e2e\"}" | head -c 400
echo

echo "==> GEPA deploy"
DEP="$(curl -fsS "${BASE}/arop/gepa/deploy" -H 'Content-Type: application/json' \
  -d "{\"candidate_id\":\"${CID}\",\"require_approval\":true}")"
echo "$DEP" | head -c 600
echo
TEACHER="$(echo "$DEP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('teacher') or '')" 2>/dev/null || true)"
if [[ -z "$TEACHER" && -f work/arop/gepa/active/teacher.json ]]; then
  TEACHER="$(python3 -c "import json; print(json.load(open('work/arop/gepa/active/teacher.json')).get('teacher',''))")"
fi
echo "teacher=${TEACHER}"

ACTIVE="work/arop/gepa/active/system_prompt.md"
if [[ ! -f "$ACTIVE" ]]; then
  echo "FAIL: missing $ACTIVE after deploy" >&2
  exit 1
fi
if grep -q '\[GEPA lesson\]:' "$ACTIVE" && [[ "$REQUIRE_HTTP_TEACHER" == "1" ]]; then
  if [[ "$TEACHER" == "mock_fallback" || "$TEACHER" == "mock" ]]; then
    echo "FAIL: expected HttpReflectionLM teacher, got ${TEACHER}" >&2
    exit 1
  fi
fi
if [[ "$REQUIRE_HTTP_TEACHER" == "1" && "$TEACHER" == "mock_fallback" ]]; then
  echo "FAIL: teacher=mock_fallback (tier LM did not rewrite)" >&2
  exit 1
fi

echo "==> chat after deploy"
CHAT="$(curl -fsS "${BASE}/v1/chat/completions" -H 'Content-Type: application/json' \
  -d '{"model":"default","messages":[{"role":"user","content":"Say hello in one short sentence."}],"max_tokens":48,"temperature":0}')"
echo "$CHAT" | python3 -c "import sys,json; d=json.load(sys.stdin); print((d.get('choices') or [{}])[0].get('message',{}).get('content','')[:300])"
BYTES="$(wc -c < "$ACTIVE" | tr -d ' ')"
echo "active_prompt_bytes=${BYTES} teacher=${TEACHER:-unknown}"
echo "OK: GEPA e2e"
