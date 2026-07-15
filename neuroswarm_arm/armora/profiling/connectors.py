"""Peer connectors — push phase timings into RPF without importing providers."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ProfileSignalBus:
    """In-process bus: peers push phase timings keyed by session_id."""

    def __init__(self) -> None:
        self._handler: Callable[..., None] | None = None
        self._session_hint: str = ""

    def bind(self, handler: Callable[..., None]) -> None:
        self._handler = handler

    def set_active_session(self, session_id: str) -> None:
        self._session_hint = session_id

    def push_phase(self, session_id: str = "", **timings: Any) -> None:
        sid = session_id or self._session_hint
        if not sid or self._handler is None:
            return
        try:
            self._handler(sid, **timings)
        except Exception as exc:
            logger.warning("rpf signal bus push failed: %s", exc)


class PhaseSignalConnector:
    """Thin adapter peers can hold — implements IPhaseSignalSource."""

    def __init__(self, bus: ProfileSignalBus) -> None:
        self.bus = bus

    def push_phase(self, session_id: str, **timings: Any) -> None:
        self.bus.push_phase(session_id, **timings)

    def record_planner(self, session_id: str, ms: float) -> None:
        self.push_phase(session_id, planner_ms=ms)

    def record_routing(self, session_id: str, ms: float) -> None:
        self.push_phase(session_id, routing_ms=ms)

    def record_execution(self, session_id: str, ms: float) -> None:
        self.push_phase(session_id, execution_ms=ms)

    def record_streaming(self, session_id: str, ms: float) -> None:
        self.push_phase(session_id, streaming_ms=ms)

    def record_backend(self, session_id: str, ms: float, *, backend: str = "") -> None:
        payload: dict[str, Any] = {"backend_ms": ms}
        if backend:
            payload["backend"] = backend
        self.push_phase(session_id, **payload)

    def record_kv(self, session_id: str, bytes_: float) -> None:
        self.push_phase(session_id, kv_memory_bytes=bytes_)

    def record_speculation(
        self,
        session_id: str,
        *,
        accepted: int = 0,
        rejected: int = 0,
    ) -> None:
        self.push_phase(
            session_id,
            accepted_speculative_tokens=accepted,
            rejected_speculative_tokens=rejected,
        )


def map_profile_to_runtime_signals(profile: Any) -> dict[str, float]:
    """Optional helper: map RuntimeProfile fields into RCIS-compatible signal deltas."""
    try:
        return {
            "cpu_seconds": float(profile.cpu.cpu_time_seconds),
            "wall_time_ms": float(profile.cpu.wall_time_ms),
            "planner_time_ms": float(profile.planner.planner_time_ms),
            "queue_time_ms": float(profile.planner.queue_time_ms),
            "execution_time_ms": float(profile.execution.execution_time_ms),
            "streaming_time_ms": float(profile.execution.streaming_time_ms),
            "peak_memory_bytes": float(profile.memory.peak_rss_bytes),
            "average_memory_bytes": float(profile.memory.average_rss_bytes),
            "kv_memory_bytes": float(profile.execution.kv_memory_bytes),
            "avg_cpu_utilization": float(profile.cpu.usage_percent),
            "accepted_speculative_tokens": float(
                profile.execution.accepted_speculative_tokens
            ),
            "rejected_speculative_tokens": float(
                profile.execution.rejected_speculative_tokens
            ),
        }
    except Exception:
        return {}
