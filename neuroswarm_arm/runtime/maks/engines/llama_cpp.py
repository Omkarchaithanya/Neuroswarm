"""llama.cpp capability adapter."""

from __future__ import annotations

from ..capability import BackendCapabilityAdapter, CapabilityFlags


def get_adapter() -> BackendCapabilityAdapter:
    return BackendCapabilityAdapter(
        backend_id="llama.cpp",
        flags=CapabilityFlags(
            prefix_reuse=True,
            shared_kv=True,
            paged_kv=False,
            speculative_kv=True,
            cross_session_reuse=True,
            cross_model_reuse=False,
        ),
    )


llama_cpp_adapter = get_adapter
