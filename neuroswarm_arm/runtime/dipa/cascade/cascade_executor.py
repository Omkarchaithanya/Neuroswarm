"""Single-tier cascade generate via the backend registry."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol

from ..interfaces.types import GenerateRequest, GenerateResult, InferenceRequest
from .cascade_policy import TierPolicy

if TYPE_CHECKING:
    from ..execution.execution_context import ExecutionContext
    from ..interfaces.backend import InferenceBackend


class SupportsBackendLookup(Protocol):
    def get(self, name: str, default: InferenceBackend | None = None) -> InferenceBackend | None: ...

    def require(self, name: str) -> InferenceBackend: ...


def approx_tokens(text: str) -> int:
    """Approximate token count by whitespace word split."""
    if not text.strip():
        return 0
    return max(1, len(text.split()))


def build_messages(req: InferenceRequest) -> list[dict[str, str]]:
    """Copy request messages, prepending ``system_prompt`` when set."""
    messages = [dict(m) for m in req.messages]
    if req.system_prompt:
        messages = [{"role": "system", "content": req.system_prompt}] + messages
    return messages


class CascadeExecutor:
    """Run one cascade tier against a registered :class:`InferenceBackend`."""

    def __init__(self, registry: SupportsBackendLookup) -> None:
        self.registry = registry

    async def generate_tier(
        self,
        req: InferenceRequest,
        tier: TierPolicy,
        ctx: ExecutionContext,
        *,
        quant: str = "",
        speculative: bool = False,
        kv_handle: str | None = None,
        max_tokens: int | None = None,
    ) -> GenerateResult:
        if hasattr(self.registry, "require"):
            backend = self.registry.require(tier.backend)
        else:
            backend = self.registry.get(tier.backend)
            if backend is None:
                raise KeyError(f"backend not registered: {tier.backend}")
        messages = build_messages(req)
        gen_req = GenerateRequest(
            messages=messages,
            max_tokens=int(max_tokens if max_tokens is not None else req.max_tokens),
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=quant or getattr(ctx, "quant", "") or "",
            stream=False,
            kv_handle=kv_handle if kv_handle is not None else getattr(ctx, "kv_handle", None),
            speculative=speculative,
        )
        t0 = time.monotonic()
        result = await backend.generate(gen_req, ctx)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        text = result.text
        prompt_tokens = result.prompt_tokens or approx_tokens(
            " ".join(str(m.get("content", "")) for m in messages)
        )
        completion_tokens = result.completion_tokens or approx_tokens(text)

        return GenerateResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=result.latency_ms or elapsed_ms,
            ttft_ms=result.ttft_ms,
            backend=result.backend or tier.backend,
            model=result.model or tier.model,
            quant=result.quant or gen_req.quant,
            tier_used=tier.id,
            raw=dict(result.raw),
            metrics=dict(result.metrics),
        )
