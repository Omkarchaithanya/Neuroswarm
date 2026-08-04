#!/usr/bin/env bash
# Create docker-compose.yaml model symlinks from whatever GGUF files exist on disk.
# Usage: MODEL_DIR=/models bash scripts/ensure-compose-models.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_MODELS=(
  "xLAM-2-1b-fc-r-Q4_0.gguf"
  "xLAM-2-3b-fc-r-Q4_0.gguf"
  "DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
)
TIER3_COMPOSE_ALIASES=(
  "Llama-3.2-8B-Instruct-Q4_K_M.gguf"
)

TIER1_SOURCES=(
  "xLAM-2-1b-fc-r-Q4_0.gguf"
  "xLAM-2-1b-fc-r-Q4_0.gguf"
  "xLAM-2-1b-fc-r-Q4_0.gguf"
)
TIER2_SOURCES=(
  "xLAM-2-3b-fc-r-Q4_0.gguf"
  "xLAM-2-3b-fc-r-Q4_0.gguf"
  "xLAM-2-3b-fc-r-Q4_0.gguf"
  "xLAM-2-3b-fc-r-Q4_0.gguf"
)
TIER3_SOURCES=(
  "DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
  "DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
  "DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
  "DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
)

resolve_model_dir() {
  local candidates=() d name score best="" best_score=0
  if [[ -n "${MODEL_DIR:-}" ]]; then
    candidates+=("$MODEL_DIR")
  fi
  if [[ -f .env ]] && grep -qE '^MODEL_DIR=' .env; then
    d="$(grep -E '^MODEL_DIR=' .env | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
    [[ -n "$d" ]] && candidates+=("$d")
  fi
  candidates+=("/models" "./models" "$ROOT/models")
  for d in "${candidates[@]}"; do
    [[ -d "$d" ]] || continue
    score=0
    for name in "${COMPOSE_MODELS[@]}"; do
      [[ -e "$d/$name" ]] && score=$((score + 1))
    done
    if [[ "$score" -gt "$best_score" ]] || { [[ "$score" -eq "$best_score" && "$score" -gt 0 && "$d" == "/models" ]]; }; then
      best="$d"
      best_score="$score"
    fi
  done
  if [[ -n "$best" && "$best_score" -gt 0 ]]; then
    echo "$best"
    return 0
  fi
  for d in "${candidates[@]}"; do
    [[ -d "$d" ]] || continue
    if compgen -G "$d/*.gguf" >/dev/null 2>&1; then
      echo "$d"
      return 0
    fi
  done
  echo "/models"
}

find_source_file() {
  local dir="$1"
  shift
  local name path
  for name in "$@"; do
    path="$dir/$name"
    if [[ -f "$path" ]]; then
      echo "$path"
      return 0
    fi
  done
  return 1
}

sync_env_model_dir() {
  local dir="$1"
  touch .env
  if grep -qE '^MODEL_DIR=' .env; then
    sed -i "s|^MODEL_DIR=.*|MODEL_DIR=${dir}|" .env
  else
    echo "MODEL_DIR=${dir}" >> .env
  fi
}

MODEL_DIR="$(resolve_model_dir)"

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "ERROR: model directory does not exist: $MODEL_DIR" >&2
  exit 1
fi

sync_env_model_dir "$MODEL_DIR"
echo "MODEL_DIR=$MODEL_DIR"

tier_sources=(TIER1_SOURCES TIER2_SOURCES TIER3_SOURCES)
missing=0
for i in 0 1 2; do
  compose_name="${COMPOSE_MODELS[$i]}"
  src_var="${tier_sources[$i]}"
  eval "sources=(\"\${${src_var}[@]}\")"

  target="$MODEL_DIR/$compose_name"
  if [[ -f "$target" && ! -L "$target" ]]; then
    echo "OK: $compose_name (regular file)"
    continue
  fi

  if source_path="$(find_source_file "$MODEL_DIR" "${sources[@]}")"; then
    ln -sfn "$(basename "$source_path")" "$target" 2>/dev/null || ln -sfn "$source_path" "$target"
    echo "Aliased: $compose_name -> $(basename "$source_path")"
    continue
  fi

  echo "MISSING: no source for $compose_name in $MODEL_DIR" >&2
  missing=1
done

tier3_target="$MODEL_DIR/${COMPOSE_MODELS[2]}"
if [[ -e "$tier3_target" ]]; then
  for alias in "${TIER3_COMPOSE_ALIASES[@]}"; do
    [[ "$alias" == "${COMPOSE_MODELS[2]}" ]] && continue
    ln -sfn "$(basename "$tier3_target")" "$MODEL_DIR/$alias" 2>/dev/null \
      || ln -sfn "$tier3_target" "$MODEL_DIR/$alias"
    echo "Aliased: $alias -> $(basename "$tier3_target")"
  done
fi

if [[ -n "${TIER3_MODEL:-}" ]]; then
  set_env_tier3="${TIER3_MODEL}"
else
  set_env_tier3="${COMPOSE_MODELS[2]}"
fi
touch .env
if grep -qE '^TIER3_MODEL=' .env; then
  sed -i "s|^TIER3_MODEL=.*|TIER3_MODEL=${set_env_tier3}|" .env
else
  echo "TIER3_MODEL=${set_env_tier3}" >> .env
fi
echo "TIER3_MODEL=${set_env_tier3} (written to .env)"

if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

echo "PASS: all compose model symlinks ready in $MODEL_DIR"
