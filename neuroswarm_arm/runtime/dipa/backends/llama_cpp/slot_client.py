"""Slot / continuous-batching client helpers for llama-server."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, parse, request


class SlotClient:
    """Best-effort llama-server slots / props probes (version-tolerant)."""

    def __init__(self, base_url: str, timeout_s: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def health(self) -> dict[str, Any]:
        for path in ("/health", "/v1/models"):
            try:
                data = self._get(path)
                return {"ok": True, "path": path, "body": data}
            except Exception as exc:  # noqa: BLE001
                last = str(exc)
        return {"ok": False, "error": last}

    def props(self) -> dict[str, Any]:
        data = self._get("/props")
        return data if isinstance(data, dict) else {}

    def metrics_text(self) -> str:
        req = request.Request(self.base_url + "/metrics", method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            raise RuntimeError(f"metrics HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"metrics unavailable: {exc.reason}") from exc

    def tokenize(self, content: str) -> list[int]:
        data = self._post("/tokenize", {"content": content})
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if isinstance(tokens, list):
            return [int(t) for t in tokens]
        return []

    def save_slot(self, id_slot: int, filename: str) -> dict[str, Any]:
        return self._post_slot_action(id_slot, "save", {"filename": filename})

    def restore_slot(self, id_slot: int, filename: str) -> dict[str, Any]:
        return self._post_slot_action(id_slot, "restore", {"filename": filename})

    def erase_slot(self, id_slot: int) -> dict[str, Any]:
        return self._post_slot_action(id_slot, "erase", {})

    def slots(self) -> list[dict[str, Any]]:
        try:
            data = self._get("/slots")
            if isinstance(data, list):
                return [s for s in data if isinstance(s, dict)]
            if isinstance(data, dict):
                slots = data.get("slots")
                if isinstance(slots, list):
                    return [s for s in slots if isinstance(s, dict)]
        except Exception:
            return []
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

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"unavailable: {exc.reason}") from exc

    def _post_slot_action(
        self, id_slot: int, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        query = parse.urlencode({"action": action})
        path = f"/slots/{int(id_slot)}?{query}"
        body = json.dumps(payload).encode("utf-8") if payload else b"{}"
        req = request.Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            raise RuntimeError(f"slots HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"slots unavailable: {exc.reason}") from exc

    def _get(self, path: str) -> Any:
        req = request.Request(self.base_url + path, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                parsed = {"error": body}
            raise RuntimeError(f"HTTP {exc.code}: {parsed}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"unavailable: {exc.reason}") from exc
