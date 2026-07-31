# ADR 0014: MLX Backend for Apple Silicon Native Inference

## Status

Accepted

## Context

Neuroswarm's DIPA runtime currently targets Arm Neoverse (Axion) via
llama.cpp with KleidiAI kernels, and x86/Linux via SGLang/vLLM.  Apple
Silicon (M3/M4/M5) is a first-class inference target for on-device
agents: unified memory, high-bandwidth Metal GPU, and strong single-
thread performance make it ideal for speculative decoding.

The `mlx-lm` ecosystem (0.21+) provides:
- Native Metal inference via Apple's MLX framework.
- OpenAI-compatible server with `mlx_lm.server --draft-model <draft>
  --num-draft-tokens N` for built-in speculative decoding.
- Hugging Face → MLX conversion tools (`mlx_lm.convert`).

Adding an MLX backend gives Neuroswarm a single-codebase path to run
locally on Apple laptops/desktops without Docker or llama.cpp.

## Decision

1. **New backend package** `neuroswarm_arm/runtime/dipa/backends/mlx/`
   with `MlxBackend(InferenceBackend)` and `MlxSpecController`.

2. **Hybrid generation**:
   - Non-speculative `generate` uses in-process `mlx_lm.generate`
     (lazy import via `asyncio.to_thread`).
   - Speculative `generate` delegates to `MlxSpecController`, which
     spawns `mlx_lm.server --draft-model … --num-draft-tokens N` and
     proxies `/v1/chat/completions`.
   - ASCR's `quality` verifier (no target forward) and `ngram`/`suffix`
     proposers provide acceptance metrics.

3. **Health**: when `NSA_MLX_MODEL_PATH` is set, probe via
   `mlx_lm.utils.load`; otherwise fall back to HTTP `/health`.

4. **Platform-gated**: Registration in `BackendFactory.register_mlx`
   checks `sys.platform == "darwin"` and
   `importlib.util.find_spec("mlx")`.  No-op on Linux.

5. **Optional dependency**: `mlx-lm>=0.21` under
   `[project.optional-dependencies] apple` (and dependency-group
   `apple`).  Install via `uv sync --extra apple`.

6. **Env-gated**: `NSA_MLX_MODEL_PATH`, `NSA_MLX_DRAFT_MODEL_PATH`,
   `NSA_MLX_NUM_DRAFT_TOKENS`, `NSA_MLX_PORT` with safe defaults.

7. **Reversible**: `strategies.yaml` gets `mlx_spec.enabled: false`.
   The system runs with the old code even if the new code fails.

8. **Streaming-first**: Primary API is `stream: true` via SSE.
   Non-stream `generate()` is fallback.

## Consequences

- Apple Silicon users get native Metal inference without Docker.
- No impact on Linux/ARM deployments — backend is never registered.
- MLX models must be converted (one-time `mlx_lm.convert`).
- The MLX server manages its own process lifecycle for speculation;
  no KleidiAI or CPU feature detection needed.
- ADR-0012 draft/verify affinity is not needed — MLX uses unified
  memory with no P/E-core split for speculation.
