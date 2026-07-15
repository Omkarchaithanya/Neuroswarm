"""SGLang HTTP client — OpenAI-compatible + PD bootstrap metadata."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(slots=True)
class SGLangHttpClient:
    base_url: str
    timeout_s: float = 120.0
    health_timeout_s: float = 5.0

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 0,
        temperature: float = 0.0,
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

    def generate(
        self,
        prompt: str,
        *,
        max_new_tokens: int = 0,
        temperature: float = 0.0,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": prompt,
            "sampling_params": {
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
            },
        }
        if extra:
            payload.update(extra)
        try:
            return self._post("/generate", payload)
        except RuntimeError:
            # Fallback to chat completions for OpenAI-only deployments.
            return self.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=max_new_tokens,
                temperature=temperature,
                extra=extra,
            )

    def is_ready(self) -> bool:
        for path in ("/health", "/v1/models"):
            try:
                self._get(path)
                return True
            except Exception:
                continue
        return False

    def metrics_text(self) -> str:
        try:
            return self._get_text("/metrics")
        except Exception:
            return ""

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
            raise RuntimeError(f"sglang HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"sglang unavailable: {exc.reason}") from exc

    def _get(self, path: str) -> dict[str, Any]:
        raw = self._get_text(path)
        if not raw:
            return {"status": "ok"}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"status": "ok", "raw": raw[:200]}

    def _get_text(self, path: str) -> str:
        req = request.Request(self.base_url.rstrip("/") + path, method="GET")
        try:
            with request.urlopen(req, timeout=self.health_timeout_s) as resp:
                return resp.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code == 404:
                raise RuntimeError("sglang endpoint not found") from exc
            raise RuntimeError(f"sglang HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"sglang unavailable: {exc.reason}") from exc


def new_bootstrap_room() -> str:
    return f"dipa-{uuid.uuid4().hex[:16]}"


def approx_tokens(messages: list[dict[str, str]]) -> int:
    return max(1, sum(len(str(m.get("content", "")).split()) for m in messages))


def extract_cached_tokens(payload: dict[str, Any]) -> int:
    usage = payload.get("usage") or {}
    for key in ("cached_tokens", "prompt_tokens_cached", "prefix_cached_tokens"):
        val = usage.get(key)
        if isinstance(val, int):
            return val
    meta = payload.get("meta_info") or {}
    val = meta.get("cached_tokens")
    if isinstance(val, int):
        return val
    return 0


def extract_prompt_tokens(payload: dict[str, Any], messages: list[dict[str, str]]) -> int:
    usage = payload.get("usage") or {}
    val = usage.get("prompt_tokens")
    if isinstance(val, int):
        return val
    meta = payload.get("meta_info") or {}
    val = meta.get("prompt_tokens")
    if isinstance(val, int):
        return val
    return approx_tokens(messages)
