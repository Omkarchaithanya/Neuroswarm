"""AgentRegistry — production capability catalog (CRUD + lookup)."""

from __future__ import annotations

import threading
from typing import Callable, Iterable

from .agent import Agent
from .exceptions import AgentNotFoundError, DuplicateAgentError
from .events import (
    AgentDisabled,
    AgentEnabled,
    AgentRegistered,
    AgentRemoved,
    AgentUpdated,
    CapabilityChanged,
    EventBus,
)
from .lifecycle import LifecycleState, transition
from .metrics import RegistryMetrics
from .registry_store import RegistryStore
from .validators import assert_not_frozen, validate_agent


class AgentRegistry:
    """Thread-safe runtime agent capability registry."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: RegistryMetrics | None = None,
        on_change: Callable[[], None] | None = None,
        allow_unknown_backend: bool = False,
        allow_unknown_quant: bool = False,
    ) -> None:
        self._store = RegistryStore()
        self._lock = threading.RLock()
        self.events = events or EventBus()
        self.metrics = metrics or RegistryMetrics()
        self._on_change = on_change
        self._allow_unknown_backend = allow_unknown_backend
        self._allow_unknown_quant = allow_unknown_quant

    # ------------------------------------------------------------------ CRUD
    def register(
        self,
        agent: Agent,
        *,
        replace_existing: bool = False,
        auto_ready: bool = True,
    ) -> Agent:
        validate_agent(
            agent,
            allow_unknown_backend=self._allow_unknown_backend,
            allow_unknown_quant=self._allow_unknown_quant,
        )
        with self._lock:
            existing = self._store.get(agent.id)
            if existing is not None and not replace_existing:
                raise DuplicateAgentError(
                    f"agent already registered: {agent.id}", field="id"
                )
            # name collision with other ids
            other = self._store.get_by_name(agent.name)
            if other is not None and other.id != agent.id:
                raise DuplicateAgentError(
                    f"duplicate agent name: {agent.name}", field="name"
                )
            if existing is not None:
                assert_not_frozen(existing)

            status = agent.status
            if auto_ready and status in {
                LifecycleState.CREATED,
                LifecycleState.REGISTERED,
                LifecycleState.LOADED,
            }:
                status = LifecycleState.READY
            elif status is LifecycleState.CREATED:
                status = LifecycleState.REGISTERED

            record = agent.model_copy(update={"status": status}).touch()
            prev = self._store.put(record)
            self.metrics.record_registration()
            self._notify()
            if prev is None:
                self.events.emit(
                    AgentRegistered(record.id, name=record.name, version=record.version)
                )
            else:
                self.events.emit(
                    AgentUpdated(record.id, name=record.name, version=record.version)
                )
            return record

    def unregister(self, agent_id: str) -> Agent:
        with self._lock:
            agent = self._store.remove(agent_id)
            if agent is None:
                raise AgentNotFoundError(agent_id)
            self._notify()
            self.events.emit(AgentRemoved(agent_id, name=agent.name))
            return agent

    def replace(
        self,
        agent: Agent,
        *,
        emit_updated: bool = True,
        skip_validation: bool = False,
    ) -> Agent:
        if not skip_validation:
            validate_agent(
                agent,
                allow_unknown_backend=self._allow_unknown_backend,
                allow_unknown_quant=self._allow_unknown_quant,
            )
        with self._lock:
            existing = self._store.get(agent.id)
            if existing is None:
                raise AgentNotFoundError(agent.id)
            if not skip_validation:
                assert_not_frozen(existing)
            other = self._store.get_by_name(agent.name)
            if other is not None and other.id != agent.id:
                raise DuplicateAgentError(
                    f"duplicate agent name: {agent.name}", field="name"
                )
            record = agent.touch()
            self._store.put(record)
            self._notify()
            if emit_updated:
                self.events.emit(
                    AgentUpdated(record.id, name=record.name, version=record.version)
                )
            return record

    def update(self, agent_id: str, **fields: object) -> Agent:
        with self._lock:
            current = self._require(agent_id)
            assert_not_frozen(current)
            data = current.model_dump(mode="python")
            data.update(fields)
            data["id"] = agent_id
            updated = Agent.model_validate(data)
            caps_changed = "capabilities" in fields or any(
                k.startswith("supported_") for k in fields
            )
            result = self.replace(updated)
            if caps_changed:
                self.events.emit(CapabilityChanged(agent_id))
            return result

    def clone(
        self,
        agent_id: str,
        *,
        new_id: str | None = None,
        new_name: str | None = None,
        register: bool = True,
    ) -> Agent:
        with self._lock:
            src = self._require(agent_id)
            cloned = src.clone(new_id_value=new_id, new_name=new_name)
            if register:
                return self.register(cloned, auto_ready=True)
            return cloned

    def freeze(self, agent_id: str) -> Agent:
        with self._lock:
            agent = self._require(agent_id)
            frozen = agent.freeze()
            return self.replace(frozen)

    def enable(self, agent_id: str) -> Agent:
        with self._lock:
            agent = self._require(agent_id)
            assert_not_frozen(agent)
            new_status = transition(agent_id, agent.status, LifecycleState.READY)
            updated = agent.with_status(new_status)
            result = self.replace(updated)
            self.events.emit(AgentEnabled(agent_id))
            return result

    def disable(self, agent_id: str) -> Agent:
        with self._lock:
            agent = self._require(agent_id)
            assert_not_frozen(agent)
            new_status = transition(agent_id, agent.status, LifecycleState.DISABLED)
            updated = agent.with_status(new_status)
            result = self.replace(updated)
            self.events.emit(AgentDisabled(agent_id))
            return result

    def set_lifecycle(self, agent_id: str, status: LifecycleState) -> Agent:
        with self._lock:
            agent = self._require(agent_id)
            assert_not_frozen(agent)
            new_status = transition(agent_id, agent.status, status)
            return self.replace(agent.with_status(new_status))

    # ---------------------------------------------------------------- lookup
    def get(self, agent_id: str) -> Agent:
        self.metrics.record_lookup()
        agent = self._store.get(agent_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent

    def get_optional(self, agent_id: str) -> Agent | None:
        self.metrics.record_lookup()
        return self._store.get(agent_id)

    def get_by_name(self, name: str) -> Agent:
        self.metrics.record_lookup()
        agent = self._store.get_by_name(name)
        if agent is None:
            raise AgentNotFoundError(name)
        return agent

    def as_list(self) -> list[Agent]:
        return self._store.all()

    def lookup_by_capability(self, key: str) -> list[Agent]:
        self.metrics.record_lookup()
        self.metrics.record_capability_hit(key)
        return self._store.by_capability(key)

    def lookup_by_model(self, model: str) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.by_model(model)

    def lookup_by_tool(self, tool: str) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.by_tool(tool)

    def lookup_by_backend(self, backend: str) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.by_backend(backend)

    def lookup_by_quantization(self, quant: str) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.by_quant(quant)

    def lookup_by_tags(self, tags: list[str], *, match_all: bool = True) -> list[Agent]:
        self.metrics.record_lookup()
        if not tags:
            return self.as_list()
        sets = [set(a.id for a in self._store.by_tag(t)) for t in tags]
        if not sets:
            return []
        ids = sets[0]
        for s in sets[1:]:
            ids = ids & s if match_all else ids | s
        by_id = {a.id: a for a in self.as_list()}
        return [by_id[i] for i in ids if i in by_id]

    def lookup_by_priority(self, priority: int) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.by_priority(priority)

    def lookup_by_health(self, band: str) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.by_health_band(band)

    def lookup_by_cost(self, max_cost: float) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.by_cost_max(max_cost)

    def lookup_by_latency(self, max_latency: float) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.by_latency_max(max_latency)

    def query(self, predicate: Callable[[Agent], bool]) -> list[Agent]:
        self.metrics.record_lookup()
        return self._store.query(predicate)

    def bulk_register(self, agents: Iterable[Agent], *, replace_existing: bool = True) -> int:
        count = 0
        for agent in agents:
            self.register(agent, replace_existing=replace_existing)
            count += 1
        return count

    def bulk_get(self, agent_ids: Iterable[str]) -> list[Agent]:
        out: list[Agent] = []
        for aid in agent_ids:
            agent = self.get_optional(aid)
            if agent is not None:
                out.append(agent)
        return out

    def history(self, agent_id: str) -> list[Agent]:
        return self._store.history(agent_id)

    def size(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._notify()

    def _require(self, agent_id: str) -> Agent:
        agent = self._store.get(agent_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()
        # refresh aggregate gauges
        agents = self._store.all()
        if agents:
            avg_health = sum(a.health.score for a in agents) / len(agents)
            avg_avail = sum(a.health.availability for a in agents) / len(agents)
            self.metrics.set_health(avg_health)
            self.metrics.set_availability(avg_avail)
        self.metrics.set_gauge("nexus_agent_registry_size", float(len(agents)))
