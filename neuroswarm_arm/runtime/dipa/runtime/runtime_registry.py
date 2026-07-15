"""Component registry for DIPA plugins."""

from __future__ import annotations

from typing import Any


class RuntimeRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def register(self, name: str, obj: Any) -> None:
        self._items[name] = obj

    def get(self, name: str, default: Any = None) -> Any:
        return self._items.get(name, default)

    def require(self, name: str) -> Any:
        if name not in self._items:
            raise KeyError(f"DIPA registry missing: {name}")
        return self._items[name]

    def names(self) -> list[str]:
        return sorted(self._items)
