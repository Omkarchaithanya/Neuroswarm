"""Session-to-slot routing for llama-server prompt execution."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.kv.utils.hashing import content_hash
from neuroswarm_arm.runtime.slot_registry import SlotRegistry, get_slot_registry


class SlotRouter:
    """Bind NeuroSwarm sessions to llama-server physical id_slot values."""

    def __init__(
        self,
        registry: SlotRegistry | None = None,
        *,
        total_slots: int = 8,
    ) -> None:
        self._registry = registry or get_slot_registry(total_slots)

    @property
    def registry(self) -> SlotRegistry:
        return self._registry

    def prepare_payload(
        self,
        session_id: str,
        prompt: str,
        base_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Inject id_slot and cache_prompt into the outgoing llama-server payload."""
        payload = dict(base_payload)
        payload["cache_prompt"] = True
        telemetry: dict[str, Any] = {
            "slot_reused": False,
            "slot_id": None,
        }

        if not session_id:
            return payload, telemetry

        prefix_hash = content_hash(prompt.encode("utf-8")) if prompt else ""
        slot_id, slot_reused = self._registry.acquire(session_id, prefix_hash=prefix_hash)
        payload["id_slot"] = int(slot_id)
        telemetry["slot_id"] = int(slot_id)
        telemetry["slot_reused"] = bool(slot_reused)
        telemetry["prefix_hash"] = prefix_hash
        return payload, telemetry

    def release(self, session_id: str) -> None:
        self._registry.release(session_id)
