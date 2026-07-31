"""DIPA inference backends — registry and concrete implementations."""

from __future__ import annotations

import importlib.util
import sys

from .executorch import ExecuTorchBackend
from .factory import BackendFactory
from .litert import LiteRTBackend
from .llama_cpp import LlamaCppBackend, LlamaHttpClient
from .mock_backend import MockBackend
from .registry import BackendRegistry
from .rtp_llm import RtpLlmBackend
from .sglang import SGLangBackend
from .vllm import VLLMBackend, VllmHttpClient

_ALL_BACKENDS: list[str] = [
    "BackendFactory",
    "BackendRegistry",
    "ExecuTorchBackend",
    "LiteRTBackend",
    "LlamaCppBackend",
    "LlamaHttpClient",
    "MockBackend",
    "RtpLlmBackend",
    "SGLangBackend",
    "VLLMBackend",
    "VllmHttpClient",
]

# MLX backend: macOS-only, requires mlx-lm (uv sync --extra apple).
if sys.platform == "darwin" and importlib.util.find_spec("mlx") is not None:
    from .mlx import MlxBackend, MlxSpecController

    _ALL_BACKENDS.extend(["MlxBackend", "MlxSpecController"])

__all__ = _ALL_BACKENDS
