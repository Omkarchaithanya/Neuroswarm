"""Component registry for HAOE extension points (no singleton abuse).

Instances are owned by HAOERuntime / factory; the registry is scoped to one
kernel instance so tests can construct isolated runtimes.
"""

from __future__ import annotations

from threading import RLock
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class RuntimeRegistry:
    """Named component lookup with optional lazy factories."""

    def __init__(self) -> None:
        self._items: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}
        self._lock = RLock()

    def register(self, name: str, obj: Any) -> None:
        with self._lock:
            self._items[name] = obj

    def register_factory(self, name: str, factory: Callable[[], Any]) -> None:
        with self._lock:
            self._factories[name] = factory

    def get(self, name: str, default: Any = None) -> Any:
        with self._lock:
            if name in self._items:
                return self._items[name]
            if name in self._factories:
                obj = self._factories[name]()
                self._items[name] = obj
                return obj
            return default

    def require(self, name: str) -> Any:
        obj = self.get(name)
        if obj is None:
            raise KeyError(f"HAOE registry missing component: {name}")
        return obj

    def names(self) -> list[str]:
        with self._lock:
            return sorted(set(self._items) | set(self._factories))
