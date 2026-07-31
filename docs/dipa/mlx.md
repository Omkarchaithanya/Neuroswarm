# MLX Backend for Apple Silicon

Native Metal inference backend for Neuroswarm on Apple Silicon (M3/M4/M5).

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  DIPA Runtime                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  ASCR    │  │ Decision │  │  MLX Backend │  │
│  │ Verifier │  │  Engine  │  │  (this doc)  │  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│       │              │               │           │
│       │         ┌────▼─────┐         │           │
│       │         │ Backend  │         │           │
│       │         │ Factory  │         │           │
│       │         └────┬─────┘         │           │
│       │              │               │           │
│       │    ┌─────────▼──────────┐    │           │
│       │    │ non-spec:          │    │           │
│       │    │ mlx_lm.generate    │◄───┘           │
│       │    │ (in-process)       │                │
│       │    └────────────────────┘                │
│       │    ┌─────────▼──────────┐                │
│       └───►│  MlxSpecController │                │
│            │  (subprocess mgr)  │                │
│            └─────────┬──────────┘                │
│                      │ HTTP                      │
└──────────────────────┼───────────────────────────┘
                       │
            ┌──────────▼──────────┐
            │   mlx_lm.server    │
            │  (Metal GPU spec)  │
            │  target + draft    │
            └────────────────────┘
```

Non-speculative `generate` loads the model via `mlx_lm.utils.load` and
calls `mlx_lm.generate` in a worker thread. Speculative requests spawn
`mlx_lm.server --draft-model` on first use.
## Setup

### Prerequisites

- macOS 14+ (Sonoma or later)
- Apple Silicon M3/M4/M5
- Python 3.11+

### Install

```bash
uv sync --extra apple
```

This installs `mlx-lm>=0.21` alongside all core dependencies.

### Model Conversion

Convert GGUF models to MLX format:

```bash
# Convert a Hugging Face model to MLX safetensors (4-bit)
python -m mlx_lm.convert \
    --hf-path meta-llama/Llama-3.2-3B-Instruct \
    --mlx-path ./models/mlx/llama-3.2-3b-instruct-4bit \
    -q

# Convert draft model
python -m mlx_lm.convert \
    --hf-path meta-llama/Llama-3.2-1B-Instruct \
    --mlx-path ./models/mlx/llama-3.2-1b-instruct-4bit \
    -q
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NSA_MLX_MODEL_PATH` | *(required)* | Path to MLX model directory |
| `NSA_MLX_DRAFT_MODEL_PATH` | *(empty)* | Path to draft model for speculation |
| `NSA_MLX_NUM_DRAFT_TOKENS` | `5` | Number of draft tokens per step |
| `NSA_MLX_PORT` | `8080` | Port for mlx_lm.server |
| `NSA_MLX_MAX_TOKENS` | `2048` | Max tokens for server context |

## Usage

### Basic (no speculation)

```python
import asyncio
from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    GenerateRequest, InferenceRequest
)

async def main():
    rt = build_dipa(backends={"mlx": MlxBackend()})
    req = GenerateRequest(
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=64,
    )
    result = await rt.infer(req)
    print(result.text)

asyncio.run(main())
```

### With Speculative Decoding

```bash
export NSA_MLX_MODEL_PATH=./models/mlx/llama-3.2-3b-instruct-4bit
export NSA_MLX_DRAFT_MODEL_PATH=./models/mlx/llama-3.2-1b-instruct-4bit
export NSA_MLX_NUM_DRAFT_TOKENS=5
```

The `MlxSpecController` spawns `mlx_lm.server` with `--draft-model` on
first use.  Speculative decoding is handled server-side — the backend
proxies to the OpenAI-compatible endpoint.

### Streaming

```python
async for chunk in backend.decode(decode_req, ctx):
    print(chunk.text, end="", flush=True)
```

## Speculative Decoding Flow

1. `MlxSpecController.start()` spawns `mlx_lm.server --model <target>
   --draft-model <draft> --num-draft-tokens 5`.
2. Backend sends requests to `/v1/chat/completions`.
3. Server performs draft→target speculation internally.
4. ASCR `quality` verifier measures acceptance rate.
5. `ngram`/`suffix` proposers available as fallback.

## Troubleshooting

### "MLX backend requires macOS with mlx-lm installed"

- Ensure `sys.platform == "darwin"`.
- Run `uv sync --extra apple`.

### Server won't start

- Check `NSA_MLX_MODEL_PATH` points to a valid MLX model directory.
- Verify `mlx_lm.server` is on PATH: `python -m mlx_lm.server --help`.

### Low acceptance rate

- Ensure draft model is from the same family as the target.
- Increase `NSA_MLX_NUM_DRAFT_TOKENS` (default 5).
- Use 4-bit quantized models for both target and draft.
