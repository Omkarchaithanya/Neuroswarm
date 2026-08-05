"""Slot / continuous-batching client helpers for llama-server."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib import error, parse, request


class SlotKVError(RuntimeError):
    """Raised when slot save/restore fails (missing file, HTTP error)."""


def _default_slot_dir() -> Path:
    return Path(os.getenv("NSA_LLAMA_SLOT_DIR", "/tmp/neuroswarm-slots"))


class SlotClient:
    """Best-effort llama-server slots / props probes (version-tolerant)."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = 5.0,
        *,
        slot_dir: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.slot_dir = slot_dir or _default_slot_dir()
        self.slot_dir.mkdir(parents=True, exist_ok=True)

    def resolve_filename(self, handle: str) -> str:
        """Map opaque kv_handle to llama-server slot filename."""
        if not handle:
            raise SlotKVError("kv_handle is empty")
        path = Path(handle)
        if path.is_absolute():
            return str(path)
        safe = handle.replace("/", "_").replace("\\", "_")
        if not safe.endswith(".kv"):
            safe = f"{safe}.kv"
        return str(self.slot_dir / safe)

    def kv_export(self, id_slot: int, handle: str) -> dict[str, Any]:
        """Thin wrapper: persist slot KV to *handle* (internal naming)."""
        return self.kv_export_to_file(id_slot, self.resolve_filename(handle))

    def kv_export_to_file(self, id_slot: int, filename: str) -> dict[str, Any]:
        """Persist slot KV to specific filesystem path."""
        try:
            return self.save_slot(id_slot, filename)
        except RuntimeError as exc:
            raise SlotKVError(
                f"kv_export_to_file failed for slot {id_slot} file {filename!r}: {exc}"
            ) from exc

    def kv_import(self, id_slot: int, handle: str) -> dict[str, Any]:
        """Thin wrapper: restore slot KV from *handle* (internal naming)."""
        return self.kv_import_from_file(id_slot, self.resolve_filename(handle))

    def kv_import_from_file(self, id_slot: int, filename: str) -> dict[str, Any]:
        """Restore slot KV from specific filesystem path."""
        if not Path(filename).is_file():
            raise SlotKVError(
                f"kv_import_from_file: slot file not found: {filename!r}"
            )
        try:
            return self.restore_slot(id_slot, filename)
        except RuntimeError as exc:
            raise SlotKVError(
                f"kv_import_from_file failed for slot {id_slot} file {filename!r}: {exc}"
            ) from exc

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

    def free_slot_count(self) -> int:
        slots = self.slots()
        if not slots:
            return 0
        return sum(
            1
            for s in slots
            if isinstance(s, dict)
            and not s.get("is_processing")
            and s.get("state") not in {"processing", "busy"}
        )

    def slot_counts(self) -> tuple[int, int]:
        """Return (free, total) slot counts from /slots."""
        slots = self.slots()
        total = len(slots)
        if total == 0:
            return 0, 0
        return self.free_slot_count(), total

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


class SlotContext:
    """Async context manager: save SOURCE slot on entry, restore TARGET on exit."""

    def __init__(
        self,
        *,
        source: SlotClient,
        target: SlotClient,
        id_slot: int,
        filename: str,
        slot_dir: Path | None = None,
    ) -> None:
        self.source = source
        self.target = target
        self.id_slot = int(id_slot)
        self.filename = source.resolve_filename(filename)
        if slot_dir is not None:
            self.source.slot_dir = slot_dir
            self.target.slot_dir = slot_dir

    async def __aenter__(self) -> SlotContext:
        await asyncio.to_thread(self.source.kv_export, self.id_slot, self.filename)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await asyncio.to_thread(self.target.kv_import, self.id_slot, self.filename)
