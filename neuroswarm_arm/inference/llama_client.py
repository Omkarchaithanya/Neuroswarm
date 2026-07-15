from __future__ import annotations

from dataclasses import dataclass
import json
from urllib import error, request


@dataclass(slots=True)
class LlamaClient:
    base_url: str

    def chat(self, messages: list[dict], max_tokens: int = 512, temperature: float = 0.2) -> dict:
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        return self._post("/v1/chat/completions", payload)

    def complete(self, prompt: str, max_tokens: int = 256) -> dict:
        return self.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)

<<<<<<< HEAD
    def is_ready(self) -> bool:
        for path in ("/health", "/v1/models"):
            try:
                self._get(path)
                return True
            except Exception:
                continue
        return False

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(f"llama server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"llama server unavailable: {exc.reason}") from exc

<<<<<<< HEAD
    def _get(self, path: str) -> dict:
        req = request.Request(self.base_url.rstrip("/") + path, method="GET")
        try:
            with request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {"status": "ok"}
        except error.HTTPError as exc:
            if exc.code == 404:
                raise RuntimeError("llama server endpoint not found") from exc
            raise RuntimeError(f"llama server HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"llama server unavailable: {exc.reason}") from exc

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
