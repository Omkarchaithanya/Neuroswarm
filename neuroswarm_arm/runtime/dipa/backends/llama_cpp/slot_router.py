"""Acquire and persist llama-server slots for session-scoped KV reuse."""

from __future__ import annotations

import re
from typing import Any

from .slot_client import SlotClient
from .slot_registry import SlotBinding, SlotRegistry, get_slot_registry


def _slot_filename(session_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", session_id)[:120]
    return f"session_{safe}.kvslot"


class SlotRouter:
    """Bind DIPA sessions to llama-server id_slot values."""

    def __init__(
        self,
        registry: SlotRegistry | None = None,
        *,
        client: SlotClient | None = None,
        tier_url: str = "",
    ) -> None:
        self._registry = registry or get_slot_registry()
        self._tier_url = tier_url.rstrip("/")
        self._client = client

    def _client_for(self, tier_url: str) -> SlotClient:
        if self._client is not None and tier_url.rstrip("/") == self._tier_url:
            return self._client
        return SlotClient(tier_url)

    def acquire(
        self,
        session_id: str,
        tier_url: str,
        *,
        action: str = "bind",
    ) -> dict[str, Any]:
        """Build llama-server chat payload extensions for slot reuse."""
        tier = tier_url.rstrip("/")
        extra: dict[str, Any] = {"cache_prompt": True}
        if not session_id:
            return extra

        client = self._client_for(tier)
        existing = self._registry.lookup(session_id, tier)
        if existing is not None:
            extra["id_slot"] = existing
            return extra

        binding = self._registry.get_binding(session_id, tier)
        if binding is not None and binding.filename:
            id_slot = self._pick_idle_slot(client, tier)
            if id_slot is not None:
                try:
                    client.restore_slot(id_slot, binding.filename)
                    self._registry.bind(session_id, id_slot, tier, filename=binding.filename)
                    extra["id_slot"] = id_slot
                    return extra
                except Exception:
                    pass

        id_slot = self._pick_idle_slot(client, tier)
        if id_slot is None:
            evicted = self._registry.evict_lru(tier)
            if evicted is not None:
                evict_session, evict_slot = evicted
                filename = _slot_filename(evict_session)
                try:
                    client.save_slot(evict_slot, filename)
                    self._registry.set_filename(evict_session, tier, filename)
                except Exception:
                    pass
                try:
                    client.erase_slot(evict_slot)
                except Exception:
                    pass
                id_slot = evict_slot
            else:
                return extra

        self._registry.bind(session_id, id_slot, tier)
        extra["id_slot"] = id_slot
        extra["_slot_action"] = action
        return extra

    def after_response(
        self,
        session_id: str,
        tier_url: str,
        raw: dict[str, Any] | None,
    ) -> SlotBinding | None:
        if not session_id:
            return None
        tier = tier_url.rstrip("/")
        id_slot = _extract_id_slot(raw)
        if id_slot is None:
            id_slot = self._registry.lookup(session_id, tier)
        if id_slot is None:
            return None
        return self._registry.bind(session_id, id_slot, tier)

    def save_session(self, session_id: str, tier_url: str) -> str | None:
        tier = tier_url.rstrip("/")
        binding = self._registry.get_binding(session_id, tier)
        if binding is None:
            return None
        filename = binding.filename or _slot_filename(session_id)
        client = self._client_for(tier)
        try:
            client.save_slot(binding.id_slot, filename)
            self._registry.set_filename(session_id, tier, filename)
            return filename
        except Exception:
            return None

    def release(self, session_id: str, tier_url: str) -> None:
        self._registry.release(session_id, tier_url.rstrip("/"))

    def _pick_idle_slot(self, client: SlotClient, tier_url: str) -> int | None:
        slots = client.slots()
        idle: list[int] = []
        for entry in slots:
            if not isinstance(entry, dict):
                continue
            sid = entry.get("id")
            if sid is None:
                continue
            busy = bool(
                entry.get("is_processing")
                or entry.get("state") in {"processing", "busy"}
            )
            if not busy:
                idle.append(int(sid))
        if not idle:
            return None
        bound = {
            b.id_slot
            for b in self._registry.snapshot()
            if b.get("tier_url") == tier_url.rstrip("/")
        }
        for candidate in sorted(idle):
            if candidate not in bound:
                return candidate
        return idle[0]


def _extract_id_slot(raw: dict[str, Any] | None) -> int | None:
    if not raw:
        return None
    for key in ("id_slot",):
        val = raw.get(key)
        if isinstance(val, int):
            return val
    usage = raw.get("usage") or {}
    if isinstance(usage, dict):
        details = usage.get("prompt_tokens_details") or {}
        if isinstance(details, dict) and "id_slot" in details:
            try:
                return int(details["id_slot"])
            except (TypeError, ValueError):
                pass
    return None
