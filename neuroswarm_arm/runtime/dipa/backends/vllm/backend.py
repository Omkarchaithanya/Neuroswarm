"""vLLM OpenAI-compatible HTTP inference backend."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from neuroswarm_arm.runtime.dipa.interfaces.backend import InferenceBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    BackendCapabilities,
    DecodeRequest,
    DeviceClass,
    GenerateRequest,
    GenerateResult,
    HealthState,
    HealthStatus,
    PrefillRequest,
    PrefillResult,
    TokenChunk,
)

from ...execution.execution_context import ExecutionContext


@dataclass(slots=True)
class VllmHttpClient:
    """Thin sync HTTP client for OpenAI-compatible vLLM servers."""

    base_url: str
    timeout_s: float = 120.0
    health_timeout_s: float = 5.0

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        return self._post("/v1/chat/completions", payload)

    def is_ready(self) -> bool:
        for path in ("/health", "/v1/models"):
            try:
                self._get(path)
                return True
            except Exception:
                continue
        return False

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(f"vllm server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"vllm server unavailable: {exc.reason}") from exc

    def _get(self, path: str) -> dict[str, Any]:
        req = request.Request(self.base_url.rstrip("/") + path, method="GET")
        try:
            with request.urlopen(req, timeout=self.health_timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {"status": "ok"}
        except error.HTTPError as exc:
            if exc.code == 404:
                raise RuntimeError("vllm server endpoint not found") from exc
            raise RuntimeError(f"vllm server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"vllm server unavailable: {exc.reason}") from exc


class VLLMBackend(InferenceBackend):
    """Async DIPA backend for an OpenAI-compatible vLLM endpoint."""

    def __init__(
        self,
        name: str = "vllm",
        base_url: str = "",
        tier: int = 0,
    ) -> None:
        self.name = name
        self.base_url = (base_url or "").strip()
        self.tier = tier
        self.capabilities = BackendCapabilities(
            streaming=True,
            batching=True,
            continuous_batching=True,
            prefill_decode_split=False,
            device_classes=(DeviceClass.GPU, DeviceClass.CPU),
        )
        self._client = (
            VllmHttpClient(base_url=self.base_url) if self.base_url else None
        )

    def _configured(self) -> bool:
        return bool(self.base_url) and self._client is not None

    async def health(self) -> HealthStatus:
        if not self._configured():
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                message="vllm endpoint not configured",
                details={"base_url": self.base_url},
            )
        assert self._client is not None
        t0 = time.perf_counter()
        ready = await asyncio.to_thread(self._client.is_ready)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if ready:
            return HealthStatus(
                state=HealthState.HEALTHY,
                latency_ms=latency_ms,
                message="vllm ready",
                details={"base_url": self.base_url},
            )
        return HealthStatus(
            state=HealthState.UNHEALTHY,
            latency_ms=latency_ms,
            message="vllm unavailable",
            details={"base_url": self.base_url},
        )

    async def prefill(self, req: PrefillRequest, ctx: ExecutionContext) -> PrefillResult:
        if not self._configured():
            raise RuntimeError("vllm unavailable")
        prompt_tokens = _approx_tokens_from_messages(req.messages)
        return PrefillResult(
            prefix_tokens=prompt_tokens,
            kv_handle=req.kv_handle,
            latency_ms=0.0,
            backend=self.name,
        )

    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
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
        words = result.text.split()
        if not words:
            yield TokenChunk(text="", index=0, finished=True)
            return
        for i, word in enumerate(words):
            piece = word if i == 0 else f" {word}"
            yield TokenChunk(
                text=piece,
                index=i,
                finished=i == len(words) - 1,
            )

    async def generate(
        self, req: GenerateRequest, ctx: ExecutionContext
    ) -> GenerateResult:
        if not self._configured() or self._client is None:
            raise RuntimeError("vllm unavailable")
        t0 = time.perf_counter()
        raw = await asyncio.to_thread(
            self._client.chat,
            req.messages,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = _extract_chat_content(raw)
        prompt_tokens = _usage_or_approx(raw, "prompt_tokens", req.messages)
        completion_tokens = _usage_or_approx_text(raw, "completion_tokens", text)
        return GenerateResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            ttft_ms=latency_ms,
            backend=self.name,
            quant=req.quant,
            tier_used=self.tier,
            raw=raw if isinstance(raw, dict) else {},
        )

    async def cancel(self, session_id: str) -> None:
        return None


def _extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    return str(content) if content is not None else ""


def _approx_word_tokens(text: str) -> int:
    return max(1, len(text.split())) if text.strip() else 0


def _approx_tokens_from_messages(messages: list[dict[str, str]]) -> int:
    parts = [str(m.get("content", "")) for m in messages]
    return _approx_word_tokens(" ".join(parts))


def _usage_or_approx(
    payload: dict[str, Any], key: str, messages: list[dict[str, str]]
) -> int:
    usage = payload.get("usage") or {}
    value = usage.get(key)
    if isinstance(value, int):
        return value
    return _approx_tokens_from_messages(messages)


def _usage_or_approx_text(payload: dict[str, Any], key: str, text: str) -> int:
    usage = payload.get("usage") or {}
    value = usage.get(key)
    if isinstance(value, int):
        return value
    return _approx_word_tokens(text)
