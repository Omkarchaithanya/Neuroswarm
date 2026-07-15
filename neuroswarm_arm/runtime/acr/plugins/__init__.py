"""ACR plugin registry — compression/planning/scoring extensions."""

from __future__ import annotations

from typing import Any, Callable


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, Callable[..., Any]]] = {
            "compression": {},
            "planning": {},
            "scoring": {},
        }

    def register(self, category: str, name: str, fn: Callable[..., Any]) -> None:
        if category not in self._plugins:
            raise KeyError(f"unknown plugin category: {category}")
        self._plugins[category][name] = fn

    def get(self, category: str, name: str) -> Callable[..., Any] | None:
        return self._plugins.get(category, {}).get(name)

    def list(self, category: str | None = None) -> dict[str, list[str]]:
        if category:
            return {category: list(self._plugins.get(category, {}))}
        return {k: list(v) for k, v in self._plugins.items()}
