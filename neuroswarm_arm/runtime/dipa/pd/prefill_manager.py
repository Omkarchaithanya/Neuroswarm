"""PrefillManager — routes prefill to SGLang (or fallback) behind HAL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neuroswarm_arm.runtime.dipa.interfaces.pd import IPrefillRuntime
from neuroswarm_arm.runtime.dipa.interfaces.types import PrefillRequest, PrefillResult

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.backends.registry import BackendRegistry
    from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext


class PrefillManager(IPrefillRuntime):
    def __init__(
        self,
        backends: BackendRegistry,
        *,
        default_backend: str = "sglang",
        metrics: Any | None = None,
        otel: Any | None = None,
        prefix_cache: Any | None = None,
    ) -> None:
        self.backends = backends
        self.default_backend = default_backend
        self.metrics = metrics
        self.otel = otel
        self.prefix_cache = prefix_cache

    def _resolve(self, name: str | None = None):
        key = name or self.default_backend
        backend = self.backends.get(key)
        if backend is None and key != "sglang":
            backend = self.backends.get("sglang")
        if backend is None:
            # Fall back to any registered backend that can prefill.
            for candidate in self.backends.all():
                backend = candidate
                break
        if backend is None:
            raise RuntimeError(f"prefill backend unavailable: {key}")
        return backend

    async def prefill(
        self, req: PrefillRequest, ctx: ExecutionContext
    ) -> PrefillResult:
        plan = getattr(ctx, "plan", None)
        name = ""
        if plan is not None:
            name = str(getattr(plan, "prefill_backend", "") or "")
        backend = self._resolve(name or None)
        span_cm = _span(self.otel, "dipa.prefill", backend=backend.name)
        with span_cm:
            result = await backend.prefill(req, ctx)
        result.messages = list(req.messages)
        result.chunk_id = req.chunk_id
        result.transfer_mode = req.transfer_mode
        if self.prefix_cache is not None and result.prefix_tokens:
            key = _prefix_key(req.messages)
            self.prefix_cache.record_hit(
                key, result.prefix_hit_tokens, result.prefix_tokens
            )
        if self.metrics is not None:
            record = getattr(self.metrics, "record_prefill", None)
            if callable(record):
                record(
                    latency_ms=result.latency_ms,
                    prefix_tokens=result.prefix_tokens,
                    hit_tokens=result.prefix_hit_tokens,
                    backend=result.backend or backend.name,
                )
        return result


def _prefix_key(messages: list[dict[str, str]]) -> str:
    parts = [f"{m.get('role', '')}:{m.get('content', '')[:128]}" for m in messages[:3]]
    return "|".join(parts)


def _span(otel: Any, name: str, **attrs: Any):
    if otel is None:
        from contextlib import nullcontext

        return nullcontext()
    span = getattr(otel, "span", None)
    if callable(span):
        return span(name, **attrs)
    from contextlib import nullcontext

    return nullcontext()
