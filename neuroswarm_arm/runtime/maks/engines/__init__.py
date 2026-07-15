"""Inference engine capability adapters (Axion-honest defaults)."""

from __future__ import annotations

from ..capability import BackendCapabilityAdapter, CapabilityFlags
from .llama_cpp import get_adapter as llama_cpp_adapter
from .sglang import get_adapter as sglang_adapter
from .vllm import get_adapter as vllm_adapter


def tensorrt_llm_adapter() -> BackendCapabilityAdapter:
    return BackendCapabilityAdapter(backend_id="tensorrt_llm", flags=CapabilityFlags())


def deepspeed_adapter() -> BackendCapabilityAdapter:
    return BackendCapabilityAdapter(backend_id="deepspeed", flags=CapabilityFlags())


def tgi_adapter() -> BackendCapabilityAdapter:
    return BackendCapabilityAdapter(
        backend_id="tgi",
        flags=CapabilityFlags(
            prefix_reuse=True,
            shared_kv=False,
            paged_kv=False,
            speculative_kv=False,
            cross_session_reuse=True,
            cross_model_reuse=False,
        ),
    )


def opaque_adapter() -> BackendCapabilityAdapter:
    return BackendCapabilityAdapter(
        backend_id="opaque",
        flags=CapabilityFlags(
            prefix_reuse=True,
            shared_kv=True,
            paged_kv=False,
            speculative_kv=False,
            cross_session_reuse=True,
            cross_model_reuse=False,
        ),
    )


def build_default_engines() -> list[BackendCapabilityAdapter]:
    return [
        opaque_adapter(),
        llama_cpp_adapter(),
        sglang_adapter(),
        vllm_adapter(),
        tensorrt_llm_adapter(),
        deepspeed_adapter(),
        tgi_adapter(),
    ]


__all__ = [
    "llama_cpp_adapter",
    "sglang_adapter",
    "vllm_adapter",
    "tensorrt_llm_adapter",
    "deepspeed_adapter",
    "tgi_adapter",
    "opaque_adapter",
    "build_default_engines",
]
