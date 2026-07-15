"""Slot / continuous-batching client helpers for llama-server."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class SlotClient:
    """Best-effort llama-server slots / props probes (version-tolerant)."""

    def __init__(self, base_url: str, timeout_s: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def slots(self) -> list[dict[str, Any]]:
        for path in ("/slots", "/props"):
            try:
                data = self._get(path)
                if path == "/slots" and isinstance(data, list):
                    return data
                if isinstance(data, dict) and "slots" in data:
                    slots = data.get("slots")
                    return list(slots) if isinstance(slots, list) else []
            except Exception:
                continue
        return []

    def busy_ratio(self) -> float:
        slots = self.slots()
        if not slots:
            return 0.0
        busy = 0
        for s in slots:
            if isinstance(s, dict) and (
                s.get("is_processing") or s.get("state") in {"processing", "busy"}
            ):
                busy += 1
        return busy / max(1, len(slots))

    def _get(self, path: str) -> Any:
        req = request.Request(self.base_url + path, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            raise RuntimeError(f"slots HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"slots unavailable: {exc.reason}") from exc
