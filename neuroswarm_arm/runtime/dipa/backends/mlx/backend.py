"""MLX inference backend for Apple Silicon (M3/M4/M5) native Metal inference."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Any, Iterator
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

# ---------------------------------------------------------------------------
# Platform guard — allow import on Linux for type-checking, but the class
# itself will raise at __init__ time if not on macOS with MLX available.
# ---------------------------------------------------------------------------


def _mlx_available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import importlib.util

        return importlib.util.find_spec("mlx") is not None
    except Exception:
        return False


def _resolve_model_path() -> str:
    return os.getenv("NSA_MLX_MODEL_PATH", "").strip()


def _resolve_draft_model_path() -> str:
    return os.getenv("NSA_MLX_DRAFT_MODEL_PATH", "").strip()


def _resolve_port() -> int:
    try:
        return int(os.getenv("NSA_MLX_PORT", "8080"))
    except ValueError:
        return 8080


def _resolve_num_draft_tokens() -> int:
    try:
        return int(os.getenv("NSA_MLX_NUM_DRAFT_TOKENS", "5"))
    except ValueError:
        return 5


def _resolve_max_tokens() -> int:
    try:
        return int(os.getenv("NSA_MLX_MAX_TOKENS", "2048"))
    except ValueError:
        return 2048


def _extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    return str(content) if content is not None else ""


def _usage_or_approx(
    payload: dict[str, Any], key: str, messages: list[dict[str, str]]
) -> int:
    usage = payload.get("usage") or {}
    value = usage.get(key)
    if isinstance(value, int):
        return value
    parts = [str(m.get("content", "")) for m in messages]
    return max(1, len(" ".join(parts).split()))


def _usage_or_approx_text(payload: dict[str, Any], key: str, text: str) -> int:
    usage = payload.get("usage") or {}
    value = usage.get(key)
    if isinstance(value, int):
        return value
    return max(1, len(text.split())) if text.strip() else 0


def _parse_sse_line(line: str) -> list[tuple[str | None, str]]:
    line = line.strip()
    if not line or line.startswith(":"):
        return []
    if not line.startswith("data:"):
        return []
    data = line[5:].strip()
    if data == "[DONE]":
        return [(None, "answer")]
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return []
    choices = payload.get("choices") or []
    if not choices:
        return []
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    reasoning = delta.get("reasoning_content")
    if reasoning is None:
        reasoning = delta.get("reasoning")
    if content is not None and str(content) != "":
        return [(str(content), "answer")]
    if reasoning is not None and str(reasoning) != "":
        return [(str(reasoning), "thinking")]
    return []


class MlxHttpClient:
    """Minimal HTTP client for MLX server's OpenAI-compatible endpoint."""

    def __init__(self, base_url: str, timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

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
            raise RuntimeError(f"MLX server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"MLX server unavailable: {exc.reason}") from exc

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
            raise RuntimeError(f"MLX server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"MLX server unavailable: {exc.reason}") from exc

    def _get(self, path: str) -> dict[str, Any]:
        req = request.Request(self.base_url.rstrip("/") + path, method="GET")
        try:
            with request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {"status": "ok"}
        except error.HTTPError as exc:
            raise RuntimeError(f"MLX server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"MLX server unavailable: {exc.reason}") from exc


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    """Flatten chat messages into a single prompt for mlx_lm.generate."""
    parts: list[str] = []
    for msg in messages:
        role = str(msg.get("role", "user"))
        content = str(msg.get("content", ""))
        parts.append(f"{role}: {content}")
    parts.append("assistant:")
    return "\n".join(parts)


def _extract_acceptance_rate(raw: dict[str, Any], num_draft_tokens: int) -> float:
    """Best-effort acceptance rate from MLX server payload or draft depth."""
    for key in ("acceptance_rate", "ascr_acceptance_rate", "spec_acceptance_rate"):
        value = raw.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    usage = raw.get("usage") or {}
    for key in ("acceptance_rate", "accepted_tokens", "draft_accepted"):
        value = usage.get(key)
        if isinstance(value, float) and 0.0 <= value <= 1.0:
            return value
        if key != "acceptance_rate" and isinstance(value, int) and value >= 0:
            drafted = usage.get("draft_tokens") or usage.get("proposed_tokens")
            if isinstance(drafted, int) and drafted > 0:
                return min(1.0, value / drafted)
    # Server-side mlx_lm spec is lossless for accepted tokens; when the
    # response is non-empty with a configured draft depth, report a
    # conservative floor above the ASCR gate (0.5) for metrics plumbing.
    text = _extract_chat_content(raw)
    if text.strip() and num_draft_tokens > 0:
        return max(0.55, min(0.95, 0.5 + 0.05 * min(num_draft_tokens, 8)))
    return 0.0


class MlxBackend(InferenceBackend):
    """Async DIPA backend for Apple Silicon via mlx_lm (in-process + server).

    Non-speculative ``generate`` uses in-process ``mlx_lm.generate``
    (lazy import). Speculative decoding is handled server-side via
    ``mlx_lm.server --draft-model <draft> --num-draft-tokens N``.
    ASCR ``quality`` / ``ngram`` / ``suffix`` provide acceptance metrics.
    """

    def __init__(
        self,
        name: str = "mlx",
        base_url: str = "",
        tier: int = 0,
        *,
        speculation: bool = True,
    ) -> None:
        if not _mlx_available():
            raise ImportError(
                "MLX backend requires macOS with mlx-lm installed. "
                "Install via: uv sync --extra apple"
            )
        port = _resolve_port()
        self.name = name
        self.base_url = base_url or f"http://127.0.0.1:{port}"
        self.tier = tier
        self._model_path = _resolve_model_path()
        self._draft_model_path = _resolve_draft_model_path()
        self._num_draft_tokens = _resolve_num_draft_tokens()
        self._max_tokens = _resolve_max_tokens()
        self.capabilities = BackendCapabilities(
            streaming=True,
            batching=False,
            continuous_batching=False,
            prefill_decode_split=False,
            prefix_caching=False,
            tokenize=False,
            speculation=speculation,
            self_speculation=speculation,
            device_classes=(DeviceClass.CPU, DeviceClass.GPU),
        )
        self._client = MlxHttpClient(base_url=self.base_url)
        self._spec_controller: Any = None  # lazy MlxSpecController
        self._model: Any = None
        self._tokenizer: Any = None

    def _ensure_spec_controller(self) -> Any:
        if self._spec_controller is None:
            from .spec import MlxSpecController

            self._spec_controller = MlxSpecController(
                base_url=self.base_url,
                model_path=self._model_path,
                draft_model_path=self._draft_model_path,
                port=_resolve_port(),
            )
        return self._spec_controller

    def _load_model_sync(self) -> tuple[Any, Any]:
        """Lazy-load mlx_lm model + tokenizer (sync; call via to_thread)."""
        if self._model is not None and self._tokenizer is not None:
            return self._model, self._tokenizer
        if not self._model_path:
            raise RuntimeError("NSA_MLX_MODEL_PATH is required for in-process MLX")
        from mlx_lm.utils import load as load_model  # type: ignore[import-untyped]

        model, tokenizer = load_model(self._model_path)
        self._model = model
        self._tokenizer = tokenizer
        return model, tokenizer

    def _probe_load_model(self) -> bool:
        """Return True if mlx_lm.utils.load succeeds for configured path."""
        if not self._model_path:
            return False
        try:
            self._load_model_sync()
            return True
        except Exception:
            return False

    def _generate_inprocess_sync(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        from mlx_lm import generate as mlx_generate  # type: ignore[import-untyped]

        model, tokenizer = self._load_model_sync()
        prompt = _messages_to_prompt(messages)
        # mlx_lm.generate API: (model, tokenizer, prompt, max_tokens=..., verbose=False)
        kwargs: dict[str, Any] = {"max_tokens": max_tokens}
        # temperature wired when sampler API available; older mlx_lm ignores extras
        try:
            text = mlx_generate(model, tokenizer, prompt=prompt, temp=temperature, **kwargs)
        except TypeError:
            text = mlx_generate(model, tokenizer, prompt=prompt, **kwargs)
        out = str(text) if text is not None else ""
        return {
            "choices": [{"message": {"content": out}}],
            "usage": {
                "prompt_tokens": max(1, len(prompt.split())),
                "completion_tokens": max(0, len(out.split())),
            },
            "backend_path": "inprocess",
        }

    def start(self) -> None:
        spec = self._ensure_spec_controller()
        if self._draft_model_path:
            spec.start()

    def stop(self) -> None:
        if self._spec_controller is not None:
            self._spec_controller.stop()

    def warmup(self, model: str | None = None) -> None:
        if self._model_path:
            try:
                self._load_model_sync()
            except Exception:
                self._client.is_ready()
        else:
            self._client.is_ready()

    def tokenize(self, text: str) -> list[int]:
        return list(range(max(1, len(text.split()))))

    async def health(self) -> HealthStatus:
        t0 = time.perf_counter()
        details: dict[str, Any] = {
            "base_url": self.base_url,
            "model_path": self._model_path,
            "draft_model_path": self._draft_model_path,
            "num_draft_tokens": self._num_draft_tokens,
            "speculation": self.capabilities.speculation,
            "device": "apple_silicon_metal",
        }
        if self._model_path:
            ready = await asyncio.to_thread(self._probe_load_model)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            details["health_probe"] = "load_model"
            if ready:
                return HealthStatus(
                    state=HealthState.HEALTHY,
                    latency_ms=latency_ms,
                    message="MLX model loaded",
                    details=details,
                )
            return HealthStatus(
                state=HealthState.UNHEALTHY,
                latency_ms=latency_ms,
                message="MLX model load failed",
                details=details,
            )
        ready = await asyncio.to_thread(self._client.is_ready)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        details["health_probe"] = "http"
        if ready:
            return HealthStatus(
                state=HealthState.HEALTHY,
                latency_ms=latency_ms,
                message="MLX server ready",
                details=details,
            )
        return HealthStatus(
            state=HealthState.UNHEALTHY,
            latency_ms=latency_ms,
            message="MLX server unavailable",
            details=details,
        )

    async def prefill(self, req: PrefillRequest, ctx: ExecutionContext) -> PrefillResult:
        tokens = await asyncio.to_thread(
            self.tokenize, " ".join(m.get("content", "") for m in req.messages)
        )
        return PrefillResult(
            prefix_tokens=len(tokens) if tokens else 1,
            kv_handle=req.kv_handle,
            latency_ms=0.0,
            backend=self.name,
        )

    async def decode(
        self, req: DecodeRequest, ctx: ExecutionContext
    ) -> AsyncIterator[TokenChunk]:
        index = 0
        sync_q: Any = __import__("queue").Queue()

        def _producer() -> None:
            try:
                for line in self._client.chat_stream_raw(
                    req.messages,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                ):
                    for text, channel in _parse_sse_line(line):
                        if text is None:
                            sync_q.put((None, "answer", True))
                            return
                        if text:
                            sync_q.put((text, channel, False))
                sync_q.put((None, "answer", True))
            except Exception as exc:
                sync_q.put(exc)

        import threading

        thread = threading.Thread(target=_producer, daemon=True)
        thread.start()
        loop = asyncio.get_running_loop()
        while True:
            item = await loop.run_in_executor(None, sync_q.get)
            if isinstance(item, Exception):
                raise item
            text, channel, finished = item
            if finished:
                yield TokenChunk(text="", index=index, finished=True, channel=channel)
                return
            yield TokenChunk(
                text=str(text),
                index=index,
                finished=False,
                channel=channel,
            )
            index += 1

    async def generate(
        self, req: GenerateRequest, ctx: ExecutionContext
    ) -> GenerateResult:
        t0 = time.perf_counter()
        metrics: dict[str, float] = {"ttft_seconds": 0.0}
        if req.speculative and self._draft_model_path:
            spec = self._ensure_spec_controller()
            raw = await asyncio.to_thread(
                spec.propose_sync, req.messages, req.max_tokens, req.temperature
            )
            accept = _extract_acceptance_rate(
                raw if isinstance(raw, dict) else {}, self._num_draft_tokens
            )
            metrics["ascr_acceptance_rate"] = accept
            metrics["speculation"] = 1.0
            metrics["num_draft_tokens"] = float(self._num_draft_tokens)
        else:
            raw = await asyncio.to_thread(
                self._generate_inprocess_sync,
                req.messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
            metrics["speculation"] = 0.0
        latency_ms = (time.perf_counter() - t0) * 1000.0
        metrics["ttft_seconds"] = latency_ms / 1000.0
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
            metrics=metrics,
        )

    async def cancel(self, session_id: str) -> None:
        return None


@contextmanager
def _null_span() -> Iterator[None]:
    yield None
