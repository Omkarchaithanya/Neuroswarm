"""Heartbeat recorder for agent liveness."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable

from .events import EventBus, HealthChanged, Heartbeat
from .health import HealthRecord

if TYPE_CHECKING:
    from .agent import Agent
    from .registry import AgentRegistry


class HeartbeatRecorder:
    """Apply heartbeats and optional failure/success observations."""

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        events: EventBus | None = None,
        on_health_change: Callable[[str, HealthRecord], None] | None = None,
    ) -> None:
        self._registry = registry
        self.events = events or EventBus()
        self._on_health_change = on_health_change
        self._lock = threading.RLock()

    def tick(self, agent_id: str) -> Agent:
        with self._lock:
            agent = self._registry.get(agent_id)
            prev = agent.health.score
            health = agent.health.touch_heartbeat()
            updated = agent.model_copy(update={"health": health}).touch()
            self._registry.replace(updated, emit_updated=False, skip_validation=True)
            self.events.emit(
                Heartbeat(
                    agent_id,
                    score=health.score,
                    availability=health.availability,
                )
            )
            if abs(health.score - prev) > 1e-9:
                self.events.emit(
                    HealthChanged(
                        agent_id,
                        previous=prev,
                        score=health.score,
                        band=health.band(),
                    )
                )
                if self._on_health_change:
                    self._on_health_change(agent_id, health)
            return updated

    def record_success(
        self,
        agent_id: str,
        *,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
    ) -> Agent:
        with self._lock:
            agent = self._registry.get(agent_id)
            prev = agent.health.score
            health = agent.health.record_success(latency_ms=latency_ms, cost_usd=cost_usd)
            updated = agent.model_copy(update={"health": health}).touch()
            self._registry.replace(updated, emit_updated=False, skip_validation=True)
            if abs(health.score - prev) > 1e-9:
                self.events.emit(
                    HealthChanged(agent_id, previous=prev, score=health.score, band=health.band())
                )
            return updated

    def record_failure(self, agent_id: str, *, message: str = "failure") -> Agent:
        with self._lock:
            agent = self._registry.get(agent_id)
            prev = agent.health.score
            health = agent.health.record_failure(message=message)
            updated = agent.model_copy(update={"health": health}).touch()
            self._registry.replace(updated, emit_updated=False, skip_validation=True)
            self.events.emit(
                HealthChanged(agent_id, previous=prev, score=health.score, band=health.band())
            )
            return updated
