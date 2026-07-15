"""SGLang capability adapter."""

from __future__ import annotations

from ..capability import BackendCapabilityAdapter, CapabilityFlags


def get_adapter() -> BackendCapabilityAdapter:
    return BackendCapabilityAdapter(
        backend_id="sglang",
        flags=CapabilityFlags(
            prefix_reuse=True,
            shared_kv=True,
            paged_kv=True,
            speculative_kv=True,
            cross_session_reuse=True,
            cross_model_reuse=False,
        ),
    )


sglang_adapter = get_adapter
