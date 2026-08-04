#!/usr/bin/env bash
# Automated llama-bench sweep for Kleidi tier images.
# Usage: bash scripts/run-llama-bench-sweep.sh
# Env: TIER=1|2|3 (default 2), THREADS, PROMPTS, NGEN, REPS
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p work/profiling
if [[ ! -w work/profiling ]]; then
  if command -v sudo >/dev/null 2>&1; then
    sudo chown -R "$(id -u):$(id -g)" work/profiling 2>/dev/null || sudo chmod -R a+rwX work/profiling 2>/dev/null || true
  fi
fi

TIER="${TIER:-2}"
THREADS="${THREADS:-2,4,8}"
PROMPTS="${PROMPTS:-128,512}"
NGEN="${NGEN:-64,128}"
REPS="${REPS:-1}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_JSON="work/profiling/llama-bench-tier${TIER}-${STAMP}.json"
OUT_MD="work/profiling/llama-bench-tier${TIER}-${STAMP}.md"
OUT_RAW="work/profiling/llama-bench-tier${TIER}-${STAMP}.raw"
SUMMARY="work/profiling/llama-bench-summary.json"

case "${TIER}" in
  1) MODEL="/models/xLAM-2-1b-fc-r-Q4_0.gguf"; SERVICE="tier1" ;;
  2) MODEL="/models/xLAM-2-3b-fc-r-Q4_0.gguf"; SERVICE="tier2" ;;
  3) MODEL="/models/DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"; SERVICE="tier3" ;;
  *) echo "TIER must be 1, 2, or 3" >&2; exit 1 ;;
esac

echo "TIER=${TIER} MODEL=${MODEL} -t ${THREADS} -p ${PROMPTS} -n ${NGEN}"

# Probe binary
if ! docker compose run --rm --no-deps --entrypoint llama-bench "${SERVICE}" -h >/tmp/llama-bench-help.txt 2>&1; then
  if grep -qiE 'executable file not found|no such file' /tmp/llama-bench-help.txt 2>/dev/null; then
    python3 - "$SUMMARY" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
  "source": "llama_bench_unavailable",
  "error": "binary_missing",
  "rows": [],
}, indent=2), encoding="utf-8")
print(f"Wrote {sys.argv[1]} source=llama_bench_unavailable")
PY
    exit 1
  fi
fi

# Prefer JSON output when supported
set +e
docker compose run --rm --no-deps --entrypoint llama-bench "${SERVICE}" \
  -m "${MODEL}" \
  -t "${THREADS}" \
  -p "${PROMPTS}" \
  -n "${NGEN}" \
  -r "${REPS}" \
  -ngl 0 \
  -o json \
  >"${OUT_RAW}" 2>&1
BENCH_RC=$?
set -e

if [[ ${BENCH_RC} -ne 0 ]] || ! grep -qE '^\s*\[|^\s*\{' "${OUT_RAW}" 2>/dev/null; then
  # Fallback: default markdown/table output
  set +e
  docker compose run --rm --no-deps --entrypoint llama-bench "${SERVICE}" \
    -m "${MODEL}" \
    -t "${THREADS}" \
    -p "${PROMPTS}" \
    -n "${NGEN}" \
    -r "${REPS}" \
    -ngl 0 \
    >"${OUT_RAW}" 2>&1
  BENCH_RC=$?
  set -e
fi

python3 - "$OUT_JSON" "$OUT_MD" "$SUMMARY" "$OUT_RAW" "$TIER" "$MODEL" "$THREADS" "$PROMPTS" "$NGEN" "$BENCH_RC" <<'PY'
import json, re, sys
from pathlib import Path

out_json, out_md, summary, raw_path, tier, model, threads, prompts, ngen, rc = sys.argv[1:11]
text = Path(raw_path).read_text(encoding="utf-8", errors="replace")
rows: list[dict] = []

# Try JSON blob (array) — skip leading docker compose warnings on stdout
parsed = None
idx = text.find("\n[")
if idx < 0 and text.lstrip().startswith("["):
    idx = text.find("[")
elif idx >= 0:
    idx = idx + 1  # point at '['
else:
    idx = text.find("[")
if idx >= 0:
    # Walk to matching closing bracket at depth 0
    depth = 0
    end = None
    for i, ch in enumerate(text[idx:], start=idx):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is not None:
        try:
            parsed = json.loads(text[idx : end + 1])
        except Exception:
            parsed = None
if parsed is None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
else:
    if isinstance(parsed, list):
        rows = [r for r in parsed if isinstance(r, dict)]
    elif isinstance(parsed, dict):
        rows = [parsed]

# Markdown / pipe table fallback: | model | size | params | backend | ngl | threads | ... | t/s |
if not rows:
    for line in text.splitlines():
        if "|" not in line or "t/s" in line.lower() and "model" in line.lower():
            continue
        if re.match(r"^\s*\|?\s*-+", line):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 6:
            continue
        # Heuristic: last numeric column is tok/s
        nums = []
        for p in parts:
            try:
                nums.append(float(p.replace(",", "")))
            except Exception:
                nums.append(None)
        tok_s = next((n for n in reversed(nums) if n is not None), None)
        if tok_s is None:
            continue
        rows.append({
            "model": parts[0],
            "threads": next((n for n in nums if n is not None and n == int(n) and 1 <= n <= 256), None),
            "n_prompt": None,
            "n_gen": None,
            "avg_ts": tok_s,
            "raw_cols": parts,
        })

payload = {
    "source": "llama_bench" if rows else ("llama_bench_unavailable" if int(rc) != 0 else "llama_bench_empty"),
    "tier": int(tier),
    "model": model,
    "matrix": {"threads": threads, "prompts": prompts, "n_gen": ngen},
    "bench_rc": int(rc),
    "rows": rows,
    "raw": raw_path,
}
Path(out_json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
Path(summary).write_text(json.dumps(payload, indent=2), encoding="utf-8")

lines = [
    f"# llama-bench tier{tier}",
    "",
    f"- model: `{model}`",
    f"- threads: `{threads}` prompts: `{prompts}` n_gen: `{ngen}`",
    f"- rows: {len(rows)}",
    "",
    "| threads | n_prompt | n_gen | tok/s |",
    "|---|---|---|---|",
]
for r in rows:
    lines.append(
        "| {t} | {p} | {n} | {s} |".format(
            t=r.get("threads") or r.get("n_threads") or "",
            p=r.get("n_prompt") or r.get("pp") or "",
            n=r.get("n_gen") or r.get("tg") or "",
            s=r.get("avg_ts") or r.get("ts") or r.get("tokens_per_second") or "",
        )
    )
Path(out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Wrote {out_json} source={payload['source']} rows={len(rows)}")
PY

echo "Done. ${OUT_JSON} ${OUT_MD}"
