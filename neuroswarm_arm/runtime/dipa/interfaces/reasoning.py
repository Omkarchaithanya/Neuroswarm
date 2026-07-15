"""Reasoning governor hook — DIPA asks, RTG owns policy (ADR connectors)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class IReasoningHook(ABC):
    """Port to Reasoning Token Governor (AIM Pillar 4).

    DIPA never imports RTG concretes. Gateway injects an adapter that
    implements this port (see ``runtime.rtg.hooks.DIPAReasoningHook``).
    """

    @abstractmethod
    def on_admit(self, request: Any, **kwargs: Any) -> Mapping[str, Any]:
        """Return thinking budget + optional system prompt / accuracy demand."""
        raise NotImplementedError

    @abstractmethod
    def on_chunk(self, session_id: str, chunk_text: str, **kwargs: Any) -> Mapping[str, Any]:
        """Per-chunk control decision (continue / early exit / escalate / …)."""
        raise NotImplementedError

    @abstractmethod
    def on_complete(self, session_id: str, final_text: str = "", **kwargs: Any) -> Mapping[str, Any]:
        """Finalize session and emit bandit / metrics feedback."""
        raise NotImplementedError


class NullReasoningHook(IReasoningHook):
    """No-op hook when RTG is disabled."""

    def on_admit(self, request: Any, **kwargs: Any) -> Mapping[str, Any]:
        cap = getattr(request, "thinking_token_cap", None) or getattr(request, "max_tokens", 4096)
        return {
            "session_id": getattr(request, "session_id", "") or "",
            "thinking_token_cap": int(cap or 4096),
            "system_prompt": "",
            "governor_accuracy_demand": 0.0,
            "force_close_message": "",
        }

    def on_chunk(self, session_id: str, chunk_text: str, **kwargs: Any) -> Mapping[str, Any]:
        return {
            "session_id": session_id,
            "action": "CONTINUE",
            "terminal": False,
            "force_close": False,
        }

    def on_complete(self, session_id: str, final_text: str = "", **kwargs: Any) -> Mapping[str, Any]:
        return {"session_id": session_id, "action": "CONTINUE", "terminal": False}
