"""Capability / tag / predicate discovery helpers."""

from __future__ import annotations

from typing import Callable, Iterable

from .agent import Agent
from .lifecycle import is_selectable
from .metadata import has_all_tags, has_any_tag


class AgentDiscovery:
    """Query helpers over a list/registry of agents."""

    def __init__(self, agents: Iterable[Agent] | Callable[[], Iterable[Agent]]) -> None:
        self._source = agents

    def _all(self) -> list[Agent]:
        src = self._source() if callable(self._source) else self._source
        return list(src)

    def by_capability_key(self, key: str) -> list[Agent]:
        return [a for a in self._all() if key in a.capabilities.capability_keys()]

    def by_task(self, task: str) -> list[Agent]:
        t = task.lower()
        return [
            a
            for a in self._all()
            if t in {x.lower() for x in a.effective_tasks()}
            or t == a.agent_type.lower()
            or t in a.tags
        ]

    def by_tags(self, tags: list[str], *, match_all: bool = True) -> list[Agent]:
        if match_all:
            return [a for a in self._all() if has_all_tags(a.tags, tags)]
        return [a for a in self._all() if has_any_tag(a.tags, tags)]

    def selectable(self) -> list[Agent]:
        return [a for a in self._all() if is_selectable(a.status)]

    def predicate(self, fn: Callable[[Agent], bool]) -> list[Agent]:
        return [a for a in self._all() if fn(a)]

    def supporting_tool(self, tool: str) -> list[Agent]:
        return [a for a in self._all() if tool in a.effective_tools()]

    def supporting_model(self, model: str) -> list[Agent]:
        return [a for a in self._all() if model in a.effective_models()]
