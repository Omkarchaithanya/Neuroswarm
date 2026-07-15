"""SGLang inference backend — dedicated prefill runtime (ADR-0006/0007)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from neuroswarm_arm.runtime.dipa.interfaces.backend import InferenceBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    BackendCapabilities,
    DecodeRequest,
    DeviceClass,
    GenerateRequest,
    GenerateResult,
    HealthState,
    HealthStatus,
    KVTransferMode,
    PrefillRequest,
    PrefillResult,
    TokenChunk,
)

from ...execution.execution_context import ExecutionContext
from .client import (
    SGLangHttpClient,
    approx_tokens,
    extract_cached_tokens,
    extract_prompt_tokens,
    new_bootstrap_room,
)
from .metrics_adapter import SGLangMetricsAdapter
from .process_supervisor import SGLangProcessSupervisor


class SGLangBackend(InferenceBackend):
    """HTTP client to SGLang OpenAI /generate APIs. Encapsulates RadixAttention."""

    def __init__(
        self,
        name: str = "sglang",
        base_url: str = "http://127.0.0.1:30000",
        tier: int = 0,
        *,
        router_url: str = "",
        native_pd: bool = False,
        supervisor: SGLangProcessSupervisor | None = None,
        managed_command: list[str] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.router_url = (router_url or "").rstrip("/")
        self.tier = tier
        self.native_pd = native_pd
        modes: tuple[KVTransferMode, ...] = (KVTransferMode.RECOMPUTE,)
        if native_pd:
            modes = (KVTransferMode.NATIVE_SGLANG, KVTransferMode.RECOMPUTE)
        self.capabilities = BackendCapabilities(
            streaming=True,
            batching=True,
            continuous_batching=True,
            prefill_decode_split=True,
            prefix_caching=True,
            chunked_prefill=True,
            radix_attention=True,
            tokenize=False,
            speculation=True,
            kv_transfer_modes=modes,
            device_classes=(DeviceClass.CPU, DeviceClass.GPU),
        )
        endpoint = self.router_url or self.base_url
        self._client = SGLangHttpClient(base_url=endpoint)
        self._prefill_client = SGLangHttpClient(base_url=self.base_url)
        self._metrics = SGLangMetricsAdapter(self._client)
        self._supervisor = supervisor
        self._managed_command = managed_command

    def start(self) -> None:
        if self._supervisor is not None and self._managed_command:
            self._supervisor.start(
                self.name,
                self._managed_command,
                base_url=self.base_url,
            )
            self._supervisor.wait_ready(
                self.name, self._prefill_client.is_ready, timeout_s=180.0
            )

    def stop(self) -> None:
        if self._supervisor is not None:
            self._supervisor.stop(self.name)

    def warmup(self, model: str | None = None) -> None:
        self._client.is_ready()

    def warmup_prefix(self, prefix_text: str) -> dict[str, Any]:
        """Warm RadixAttention by running a zero-token prefill on the prefix."""
        t0 = time.perf_counter()
        try:
            raw = self._prefill_client.chat(
                [{"role": "system", "content": prefix_text}],
                max_tokens=0,
                temperature=0.0,
            )
            hit = extract_cached_tokens(raw)
            return {
                "ok": True,
                "cached_tokens": hit,
                "latency_ms": (time.perf_counter() - t0) * 1000.0,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def health(self) -> HealthStatus:
        t0 = time.perf_counter()
        ready = await asyncio.to_thread(self._prefill_client.is_ready)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        details: dict[str, Any] = {
            "base_url": self.base_url,
            "router_url": self.router_url,
            "native_pd": self.native_pd,
            "radix_attention": True,
            "chunked_prefill": True,
            "continuous_batching": True,
        }
        if self._supervisor is not None:
            details["supervisor"] = self._supervisor.snapshot().get(self.name, {})
        scraped = await asyncio.to_thread(self._metrics.scrape)
        if scraped:
            details["prometheus_keys"] = len(scraped)
        if not ready:
            details["feature"] = "UNAVAILABLE"
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                latency_ms=latency_ms,
                message="sglang unavailable",
                details=details,
            )
        return HealthStatus(
            state=HealthState.HEALTHY,
            latency_ms=latency_ms,
            message="sglang ready",
            details=details,
        )

    async def prefill(self, req: PrefillRequest, ctx: ExecutionContext) -> PrefillResult:
        t0 = time.perf_counter()
        room = new_bootstrap_room() if self.native_pd else ""
        extra: dict[str, Any] = {}
        if room:
            extra["bootstrap_room"] = room
        # max_tokens=0 → prefill / prompt processing only when server supports it.
        raw = await asyncio.to_thread(
            self._prefill_client.chat,
            req.messages,
            max_tokens=0,
            temperature=0.0,
            stream=False,
            extra=extra or None,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        prompt_tokens = extract_prompt_tokens(raw, req.messages)
        hit = extract_cached_tokens(raw)
        mode = (
            KVTransferMode.NATIVE_SGLANG
            if self.native_pd
            else (req.transfer_mode or KVTransferMode.RECOMPUTE)
        )
        return PrefillResult(
            prefix_tokens=prompt_tokens or approx_tokens(req.messages),
            kv_handle=req.kv_handle or (f"sglang:{room}" if room else None),
            latency_ms=latency_ms,
            backend=self.name,
            prefix_hit_tokens=hit,
            chunk_id=req.chunk_id,
            transfer_mode=mode,
            radix_node_id=str((raw.get("meta_info") or {}).get("radix_node", "")),
            bootstrap_room=room,
            messages=list(req.messages),
            metrics={
                "cached_tokens": float(hit),
                "prompt_tokens": float(prompt_tokens),
            },
        )

    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        # Decode on SGLang only for native same-engine PD; soft mode uses llama.cpp.
        result = await self.generate(
            GenerateRequest(
                messages=req.messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                session_id=req.session_id,
                quant=req.quant,
                stream=False,
                kv_handle=req.kv_handle,
            ),
            ctx,
        )
        if result.text:
            yield TokenChunk(text=result.text, index=0, finished=False)
        yield TokenChunk(text="", index=1, finished=True)

    async def generate(
        self, req: GenerateRequest, ctx: ExecutionContext
    ) -> GenerateResult:
        t0 = time.perf_counter()
        raw = await asyncio.to_thread(
            self._client.chat,
            req.messages,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            stream=False,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = _extract_chat_content(raw)
        prompt_tokens = extract_prompt_tokens(raw, req.messages)
        usage = raw.get("usage") or {}
        completion = usage.get("completion_tokens")
        if not isinstance(completion, int):
            completion = max(1, len(text.split())) if text else 0
        return GenerateResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=int(completion),
            latency_ms=latency_ms,
            ttft_ms=latency_ms,
            backend=self.name,
            quant=req.quant,
            tier_used=self.tier,
            raw=raw if isinstance(raw, dict) else {},
            metrics={"cached_tokens": float(extract_cached_tokens(raw))},
        )

    async def cancel(self, session_id: str) -> None:
        return None


def _extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        # /generate style
        if "text" in payload:
            return str(payload.get("text") or "")
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    return str(content) if content is not None else ""
