"""llama.cpp OpenAI-compatible inference backend (managed-process aware)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
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
from ...control.telemetry_exporter import TelemetryExporter
from .kleidiai_verifier import KleidiaiVerifier
from .process_supervisor import ProcessSupervisor
from .slot_client import SlotClient
from .slot_router import SlotRouter


@dataclass(slots=True)
class LlamaHttpClient:
    """HTTP client for OpenAI-compatible llama.cpp servers."""

    base_url: str
    timeout_s: float = 120.0
    health_timeout_s: float = 5.0

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stream: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if extra:
            payload.update(extra)
        return self._post("/v1/chat/completions", payload)

    def chat_stream_raw(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.2,
        extra: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        payload: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if extra:
            payload.update(extra)
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url.rstrip("/") + "/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    yield line.decode("utf-8", errors="ignore")
        except error.HTTPError as exc:
            raise RuntimeError(f"llama server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"llama server unavailable: {exc.reason}") from exc

    def is_ready(self) -> bool:
        for path in ("/health", "/v1/models"):
            try:
                self._get(path)
                return True
            except Exception:
                continue
        return False

    def tokenize(self, content: str) -> list[int] | None:
        try:
            data = self._post("/tokenize", {"content": content})
            tokens = data.get("tokens")
            if isinstance(tokens, list):
                return [int(t) for t in tokens]
        except Exception:
            return None
        return None

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
            raise RuntimeError(f"llama server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"llama server unavailable: {exc.reason}") from exc

    def _get(self, path: str) -> dict[str, Any]:
        req = request.Request(self.base_url.rstrip("/") + path, method="GET")
        try:
            with request.urlopen(req, timeout=self.health_timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {"status": "ok"}
        except error.HTTPError as exc:
            if exc.code == 404:
                raise RuntimeError("llama server endpoint not found") from exc
            raise RuntimeError(f"llama server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"llama server unavailable: {exc.reason}") from exc


class LlamaCppBackend(InferenceBackend):
    """Async DIPA backend for llama.cpp server (HTTP + optional process ownership)."""

    def __init__(
        self,
        name: str = "llama_cpp",
        base_url: str = "http://127.0.0.1:8080",
        tier: int = 0,
        *,
        kleidiai: bool | None = None,
        continuous_batching: bool = True,
        prefix_caching: bool = True,
        speculation: bool = False,
        supervisor: ProcessSupervisor | None = None,
        managed_command: list[str] | None = None,
        numa_bind: list[str] | None = None,
        telemetry: TelemetryExporter | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url
        self.tier = tier
        env_k = os.getenv("NSA_DIPA_KLEIDIAI", "").strip() in {"1", "true", "TRUE", "yes"}
        self._kleidiai = env_k if kleidiai is None else kleidiai
        self.capabilities = BackendCapabilities(
            streaming=True,
            batching=True,
            continuous_batching=continuous_batching,
            prefill_decode_split=False,  # honest: OpenAI chat path is fused
            prefix_caching=prefix_caching,
            tokenize=True,
            speculation=speculation,
            self_speculation=speculation,
            kleidiai=self._kleidiai,
            device_classes=(DeviceClass.CPU,),
        )
        self._client = LlamaHttpClient(base_url=base_url)
        self._slots = SlotClient(base_url)
        self._slot_router = SlotRouter(client=self._slots, tier_url=base_url)
        self._telemetry = telemetry
        self._supervisor = supervisor
        self._managed_command = managed_command
        self._numa_bind = numa_bind
        self._verifier = KleidiaiVerifier(
            require=os.getenv("NSA_REQUIRE_KLEIDIAI", "0").strip()
            in {"1", "true", "TRUE", "yes"}
        )

    def start(self) -> None:
        if self._supervisor is not None and self._managed_command:
            self._supervisor.start(
                self.name,
                self._managed_command,
                base_url=self.base_url,
                numa_bind=self._numa_bind,
            )
            ok = self._supervisor.wait_kleidiai(self.name, timeout_s=180.0)
            self.capabilities.kleidiai = bool(ok or self._kleidiai)

    def stop(self) -> None:
        if self._supervisor is not None:
            self._supervisor.stop(self.name)

    def warmup(self, model: str | None = None) -> None:
        self._client.is_ready()

    def tokenize(self, text: str) -> list[int]:
        tokens = self._client.tokenize(text)
        if tokens is not None:
            return tokens
        return list(range(max(1, len(text.split()))))

    async def health(self) -> HealthStatus:
        t0 = time.perf_counter()
        ready = await asyncio.to_thread(self._client.is_ready)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        details: dict[str, Any] = {
            "base_url": self.base_url,
            "kleidiai": self.capabilities.kleidiai,
            "continuous_batching": self.capabilities.continuous_batching,
            "prefix_caching": self.capabilities.prefix_caching,
            "prefill_decode_split": self.capabilities.prefill_decode_split,
        }
        if self._supervisor is not None:
            details["supervisor"] = self._supervisor.snapshot().get(self.name, {})
        if ready:
            try:
                details["slot_busy_ratio"] = await asyncio.to_thread(
                    self._slots.busy_ratio
                )
            except Exception:
                pass
            return HealthStatus(
                state=HealthState.HEALTHY,
                latency_ms=latency_ms,
                message="llama.cpp ready",
                details=details,
            )
        return HealthStatus(
            state=HealthState.UNHEALTHY,
            latency_ms=latency_ms,
            message="llama.cpp unavailable",
            details=details,
        )

    async def prefill(self, req: PrefillRequest, ctx: ExecutionContext) -> PrefillResult:
        # Honest fused path: no separate server prefill API on chat endpoint.
        prompt_tokens = _approx_tokens_from_messages(req.messages)
        tokens = await asyncio.to_thread(
            self.tokenize, " ".join(m.get("content", "") for m in req.messages)
        )
        return PrefillResult(
            prefix_tokens=len(tokens) if tokens else prompt_tokens,
            kv_handle=req.kv_handle,
            latency_ms=0.0,
            backend=self.name,
        )

    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        index = 0
        extra = _llama_chat_extra(
            session_id=req.session_id,
            slot_router=self._slot_router,
            tier_url=self.base_url,
        )

        def _iter() -> Iterator[TokenChunk]:
            nonlocal index
            finished = False
            for line in self._client.chat_stream_raw(
                req.messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                extra=extra,
            ):
                for piece in _parse_sse_line(line):
                    if piece is None:
                        finished = True
                        yield TokenChunk(text="", index=index, finished=True)
                        return
                    if piece:
                        yield TokenChunk(text=piece, index=index, finished=False)
                        index += 1
            if not finished:
                yield TokenChunk(text="", index=index, finished=True)

        for chunk in await asyncio.to_thread(lambda: list(_iter())):
            yield chunk

    async def generate(
        self, req: GenerateRequest, ctx: ExecutionContext
    ) -> GenerateResult:
        t0 = time.perf_counter()
        extra = _llama_chat_extra(
            session_id=req.session_id,
            slot_router=self._slot_router,
            tier_url=self.base_url,
        )
        slot_action = str(extra.pop("_slot_action", "bind"))
        span_attrs = {
            "session_id": req.session_id,
            "backend": self.name,
            "tier": self.tier,
            "slot.action": slot_action,
        }
        if "id_slot" in extra:
            span_attrs["slot.id"] = extra["id_slot"]
        tel = self._telemetry
        with tel.span("chat", **span_attrs) if tel else _null_span():
            raw = await asyncio.to_thread(
                self._client.chat,
                req.messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=False,
                extra=extra,
            )
        self._slot_router.after_response(req.session_id, self.base_url, raw)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = _extract_chat_content(raw)
        prompt_tokens = _usage_or_approx(raw, "prompt_tokens", req.messages)
        completion_tokens = _usage_or_approx_text(raw, "completion_tokens", text)
        cached_tokens = _cached_prompt_tokens(raw)
        id_slot = raw.get("id_slot") if isinstance(raw, dict) else None
        metrics = {
            "cached_prompt_tokens": float(cached_tokens),
        }
        if isinstance(id_slot, int):
            metrics["id_slot"] = float(id_slot)
        if tel:
            tel.event(
                "neuroswarm.slot.bind",
                session_id=req.session_id,
                slot_id=id_slot,
                tier=self.tier,
                slot_action=slot_action,
            )
            if cached_tokens:
                tel.event(
                    "gen_ai.cache_read",
                    session_id=req.session_id,
                    cached_tokens=cached_tokens,
                    gen_ai_usage_cache_read_input_tokens=cached_tokens,
                )
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
            metrics=metrics,
        )

    async def cancel(self, session_id: str) -> None:
        # llama-server cancel is slot-specific; best-effort no-op when unmanaged.
        return None


def _llama_chat_extra(
    *,
    session_id: str = "",
    slot_router: SlotRouter | None = None,
    tier_url: str = "",
) -> dict[str, Any]:
    """Build llama-server slot reuse payload (id_slot + cache_prompt)."""
    if slot_router is not None and session_id:
        return slot_router.acquire(session_id, tier_url)
    return {"cache_prompt": True}


def _cached_prompt_tokens(payload: dict[str, Any]) -> int:
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        return 0
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached = details.get("cached_tokens")
        if isinstance(cached, int):
            return cached
    return 0


@contextmanager
def _null_span() -> Iterator[None]:
    yield None


def _parse_sse_line(line: str) -> list[str | None]:
    """Return text pieces; None sentinel means stream done."""
    line = line.strip()
    if not line or line.startswith(":"):
        return []
    if not line.startswith("data:"):
        return []
    data = line[5:].strip()
    if data == "[DONE]":
        return [None]
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return []
    choices = payload.get("choices") or []
    if not choices:
        return []
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if content is None:
        return []
    return [str(content)]


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
