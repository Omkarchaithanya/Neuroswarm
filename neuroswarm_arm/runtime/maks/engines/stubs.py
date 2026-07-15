"""TensorRT-LLM / DeepSpeed / TGI stub adapters."""

from __future__ import annotations

from . import deepspeed_adapter, tensorrt_llm_adapter, tgi_adapter

__all__ = ["tensorrt_llm_adapter", "deepspeed_adapter", "tgi_adapter"]
