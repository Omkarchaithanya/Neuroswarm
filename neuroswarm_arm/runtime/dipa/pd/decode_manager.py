"""DecodeManager — llama.cpp (or configured) decode behind HAL."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from neuroswarm_arm.runtime.dipa.interfaces.pd import DecodeHandle, IDecodeRuntime
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    DecodeRequest,
    GenerateRequest,
    GenerateResult,
    TokenChunk,
)

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.backends.registry import BackendRegistry
    from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext


class DecodeManager(IDecodeRuntime):
    def __init__(
        self,
        backends: BackendRegistry,
        *,
        default_backend: str = "llama_cpp",
        metrics: Any | None = None,
        otel: Any | None = None,
    ) -> None:
        self.backends = backends
        self.default_backend = default_backend
        self.metrics = metrics
        self.otel = otel

    def _resolve(self, name: str | None = None):
        key = name or self.default_backend
        backend = self.backends.get(key)
        if backend is None:
            # Cascade tiers register as tier1/tier2/tier3 — prefer tier2 then any llama.
            for candidate_name in ("tier2", "tier1", "tier3", "llama_cpp", "mock"):
                backend = self.backends.get(candidate_name)
                if backend is not None:
                    break
        if backend is None:
            for candidate in self.backends.all():
                backend = candidate
                break
        if backend is None:
            raise RuntimeError(f"decode backend unavailable: {key}")
        return backend

    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        plan = getattr(ctx, "plan", None)
        name = ""
        if plan is not None:
            name = str(getattr(plan, "decode_backend", "") or "")
        backend = self._resolve(name or None)
        span_cm = _span(self.otel, "dipa.decode", backend=backend.name)
        with span_cm:
            async for chunk in backend.decode(req, ctx):
                yield chunk

    async def generate_from_handle(
        self,
        handle: DecodeHandle,
        *,
        max_tokens: int,
        temperature: float,
        ctx: ExecutionContext,
    ) -> GenerateResult:
        backend = self._resolve(handle.decode_backend or None)
        span_cm = _span(
            self.otel,
            "dipa.decode",
            backend=backend.name,
            transfer_mode=handle.transfer_mode.value,
        )
        with span_cm:
            gen = GenerateRequest(
                messages=handle.messages,
                max_tokens=max_tokens,
                temperature=temperature,
                session_id=handle.session_id,
                quant=handle.quant,
                stream=False,
                kv_handle=handle.kv_handle,
            )
            result = await backend.generate(gen, ctx)
        result.metrics = dict(result.metrics)
        result.metrics["kv_transfer_mode"] = _mode_code(handle.transfer_mode.value)
        result.metrics["prefix_hit_tokens"] = float(handle.prefix_hit_tokens)
        result.metrics["recompute_tokens"] = float(handle.recompute_tokens)
        result.metrics["prefix_tokens"] = float(handle.prefix_tokens)
        result.metrics["chunk_count"] = float(handle.metadata.get("chunk_count", 1.0))
        if self.metrics is not None:
            record = getattr(self.metrics, "record_decode", None)
            if callable(record):
                record(
                    latency_ms=result.latency_ms,
                    completion_tokens=result.completion_tokens,
                    recompute_tokens=handle.recompute_tokens,
                    transfer_mode=handle.transfer_mode.value,
                    backend=result.backend or backend.name,
                )
        return result

    async def stream_from_handle(
        self,
        handle: DecodeHandle,
        *,
        max_tokens: int,
        temperature: float,
        ctx: ExecutionContext,
    ) -> AsyncIterator[TokenChunk]:
        req = DecodeRequest(
            messages=handle.messages,
            max_tokens=max_tokens,
            temperature=temperature,
            session_id=handle.session_id,
            quant=handle.quant,
            kv_handle=handle.kv_handle,
            stream=True,
            transfer_mode=handle.transfer_mode,
            bootstrap_room=handle.bootstrap_room,
            radix_node_id=handle.radix_node_id,
            prefix_hit_tokens=handle.prefix_hit_tokens,
            recompute_tokens=handle.recompute_tokens,
            token_ids=list(handle.token_ids),
        )
        async for chunk in self.decode(req, ctx):
            yield chunk


def _mode_code(mode: str) -> float:
    return {"native_sglang": 1.0, "recompute": 2.0, "unavailable": 3.0}.get(mode, 0.0)


def _span(otel: Any, name: str, **attrs: Any):
    if otel is None:
        from contextlib import nullcontext

        return nullcontext()
    span = getattr(otel, "span", None)
    if callable(span):
        return span(name, **attrs)
    from contextlib import nullcontext

    return nullcontext()
