"""In-memory store with secondary indexes for Agent Registry."""

from __future__ import annotations

import threading
from typing import Callable, Iterable

from .agent import Agent


class RegistryStore:
    """Primary map + secondary indexes. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._agents: dict[str, Agent] = {}
        self._by_name: dict[str, str] = {}  # lower name -> id
        self._by_namespace: dict[str, set[str]] = {}
        self._by_tag: dict[str, set[str]] = {}
        self._by_tool: dict[str, set[str]] = {}
        self._by_model: dict[str, set[str]] = {}
        self._by_backend: dict[str, set[str]] = {}
        self._by_quant: dict[str, set[str]] = {}
        self._by_capability: dict[str, set[str]] = {}
        self._by_priority: dict[int, set[str]] = {}
        self._by_health_band: dict[str, set[str]] = {}
        self._versions: dict[str, list[Agent]] = {}

    def __len__(self) -> int:
        with self._lock:
            return len(self._agents)

    def ids(self) -> list[str]:
        with self._lock:
            return list(self._agents.keys())

    def all(self) -> list[Agent]:
        with self._lock:
            return list(self._agents.values())

    def get(self, agent_id: str) -> Agent | None:
        with self._lock:
            return self._agents.get(agent_id)

    def get_by_name(self, name: str) -> Agent | None:
        with self._lock:
            aid = self._by_name.get(name.lower())
            return self._agents.get(aid) if aid else None

    def put(self, agent: Agent, *, keep_history: bool = True) -> Agent | None:
        """Insert or replace. Returns previous agent if any."""
        with self._lock:
            previous = self._agents.get(agent.id)
            if previous is not None:
                self._unindex(previous)
                if keep_history:
                    self._versions.setdefault(agent.id, []).append(previous)
            self._agents[agent.id] = agent
            self._index(agent)
            return previous

    def remove(self, agent_id: str) -> Agent | None:
        with self._lock:
            agent = self._agents.pop(agent_id, None)
            if agent is None:
                return None
            self._unindex(agent)
            return agent

    def history(self, agent_id: str) -> list[Agent]:
        with self._lock:
            return list(self._versions.get(agent_id, []))

    def clear(self) -> None:
        with self._lock:
            self._agents.clear()
            self._by_name.clear()
            self._by_namespace.clear()
            self._by_tag.clear()
            self._by_tool.clear()
            self._by_model.clear()
            self._by_backend.clear()
            self._by_quant.clear()
            self._by_capability.clear()
            self._by_priority.clear()
            self._by_health_band.clear()
            self._versions.clear()

    def existing_names(self) -> list[str]:
        with self._lock:
            return [a.name for a in self._agents.values()]

    def query(self, predicate: Callable[[Agent], bool]) -> list[Agent]:
        with self._lock:
            return [a for a in self._agents.values() if predicate(a)]

    def by_tag(self, tag: str) -> list[Agent]:
        return self._resolve(self._by_tag.get(tag.lower(), set()))

    def by_tool(self, tool: str) -> list[Agent]:
        return self._resolve(self._by_tool.get(tool, set()))

    def by_model(self, model: str) -> list[Agent]:
        return self._resolve(self._by_model.get(model, set()))

    def by_backend(self, backend: str) -> list[Agent]:
        return self._resolve(self._by_backend.get(backend.lower(), set()))

    def by_quant(self, quant: str) -> list[Agent]:
        return self._resolve(self._by_quant.get(quant.lower(), set()))

    def by_capability(self, key: str) -> list[Agent]:
        return self._resolve(self._by_capability.get(key, set()))

    def by_namespace(self, namespace: str) -> list[Agent]:
        return self._resolve(self._by_namespace.get(namespace, set()))

    def by_priority(self, priority: int) -> list[Agent]:
        return self._resolve(self._by_priority.get(priority, set()))

    def by_health_band(self, band: str) -> list[Agent]:
        return self._resolve(self._by_health_band.get(band, set()))

    def by_cost_max(self, max_cost: float) -> list[Agent]:
        with self._lock:
            return [a for a in self._agents.values() if a.estimated_cost <= max_cost]

    def by_latency_max(self, max_latency: float) -> list[Agent]:
        with self._lock:
            return [a for a in self._agents.values() if a.estimated_latency <= max_latency]

    def _resolve(self, ids: Iterable[str]) -> list[Agent]:
        with self._lock:
            return [self._agents[i] for i in ids if i in self._agents]

    def _index(self, agent: Agent) -> None:
        self._by_name[agent.name.lower()] = agent.id
        self._by_namespace.setdefault(agent.namespace, set()).add(agent.id)
        self._by_priority.setdefault(agent.priority, set()).add(agent.id)
        self._by_health_band.setdefault(agent.health.band(), set()).add(agent.id)
        for tag in agent.tags:
            self._by_tag.setdefault(tag.lower(), set()).add(agent.id)
        for tool in agent.effective_tools():
            self._by_tool.setdefault(tool, set()).add(agent.id)
        for model in agent.effective_models():
            self._by_model.setdefault(model, set()).add(agent.id)
        for backend in agent.effective_backends():
            self._by_backend.setdefault(backend.lower(), set()).add(agent.id)
        for quant in agent.effective_quants():
            self._by_quant.setdefault(quant.lower(), set()).add(agent.id)
        for key in agent.capabilities.capability_keys():
            self._by_capability.setdefault(key, set()).add(agent.id)
        for task in agent.effective_tasks():
            self._by_capability.setdefault(f"task:{task}", set()).add(agent.id)

    def _unindex(self, agent: Agent) -> None:
        if self._by_name.get(agent.name.lower()) == agent.id:
            del self._by_name[agent.name.lower()]
        self._discard(self._by_namespace, agent.namespace, agent.id)
        self._discard(self._by_priority, agent.priority, agent.id)
        self._discard(self._by_health_band, agent.health.band(), agent.id)
        for tag in agent.tags:
            self._discard(self._by_tag, tag.lower(), agent.id)
        for tool in agent.effective_tools():
            self._discard(self._by_tool, tool, agent.id)
        for model in agent.effective_models():
            self._discard(self._by_model, model, agent.id)
        for backend in agent.effective_backends():
            self._discard(self._by_backend, backend.lower(), agent.id)
        for quant in agent.effective_quants():
            self._discard(self._by_quant, quant.lower(), agent.id)
        for key in agent.capabilities.capability_keys():
            self._discard(self._by_capability, key, agent.id)
        for task in agent.effective_tasks():
            self._discard(self._by_capability, f"task:{task}", agent.id)

    @staticmethod
    def _discard(index: dict, key: object, agent_id: str) -> None:
        s = index.get(key)  # type: ignore[arg-type]
        if s is None:
            return
        s.discard(agent_id)
        if not s:
            del index[key]  # type: ignore[arg-type]
