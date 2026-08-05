#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/models}"
MANIFEST=""
DEMO_SOURCE=""
SOURCE_DIR=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/prepare-models.sh --manifest models/manifest.example.yaml
  bash scripts/prepare-models.sh --demo-source /models/small-demo.gguf
  bash scripts/prepare-models.sh --source-dir /models

The manifest documents expected model files and optional checksums. This script
does not download gated models; place GGUF files in /models first, then validate.
The source-dir mode maps the real model filenames used by this project to the
canonical filenames expected by docker-compose.yaml.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest)
      MANIFEST="$2"
      shift 2
      ;;
    --demo-source)
      DEMO_SOURCE="$2"
      shift 2
      ;;
    --source-dir)
      SOURCE_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -d "$MODEL_DIR" ]]; then
  :
elif ! mkdir -p "$MODEL_DIR" 2>/dev/null; then
  sudo mkdir -p "$MODEL_DIR"
  sudo chown "$USER:$USER" "$MODEL_DIR"
fi

expected=(
  "xLAM-2-1B-fc-r-Q4_0.gguf"
  "xLAM-2-3B-fc-r-Q4_0.gguf"
  "DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
)

source_files=(
  "xLAM-2-1B-fc-r-Q4_0.gguf"
  "xLAM-2-3B-fc-r-Q4_0.gguf"
  "DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf"
)

missing=0

if [[ -n "$DEMO_SOURCE" ]]; then
  if [[ ! -f "$DEMO_SOURCE" ]]; then
    echo "Demo source model does not exist: $DEMO_SOURCE" >&2
    exit 1
  fi
  for name in "${expected[@]}"; do
    ln -sfn "$DEMO_SOURCE" "$MODEL_DIR/$name"
  done
  echo "Created demo symlinks in $MODEL_DIR. Replace these with real tiered models for final benchmarks."
fi

if [[ -n "$SOURCE_DIR" ]]; then
  if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "Source directory does not exist: $SOURCE_DIR" >&2
    exit 1
  fi

  for i in "${!expected[@]}"; do
    source_path="$SOURCE_DIR/${source_files[$i]}"
    target_path="$MODEL_DIR/${expected[$i]}"
    if [[ ! -f "$source_path" ]]; then
      echo "Missing source model: $source_path" >&2
      missing=1
      continue
    fi
    if [[ "$source_path" == "$target_path" ]]; then
      echo "Source already canonical: $target_path"
    else
      ln -sfn "$source_path" "$target_path"
      echo "Aliased: $target_path -> $source_path"
    fi
  done
fi

for name in "${expected[@]}"; do
  path="$MODEL_DIR/$name"
  if [[ ! -e "$path" ]]; then
    echo "Missing: $path" >&2
    missing=1
  else
    echo "Found: $path"
  fi
done

if [[ -n "$MANIFEST" && -f "$MANIFEST" ]]; then
  echo "Manifest present: $MANIFEST"
  echo "Checksums are documented there; add sha256sum commands once real model hashes are chosen."
fi

exit "$missing"
