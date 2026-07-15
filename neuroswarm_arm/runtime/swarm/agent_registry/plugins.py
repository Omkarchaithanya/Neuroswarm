"""Plugin architecture for external agent registration (no downloads)."""

from __future__ import annotations

import importlib
import threading
from typing import Protocol, runtime_checkable

from .agent import Agent
from .exceptions import PluginError


@runtime_checkable
class IAgentPlugin(Protocol):
    """External agent plugin contract.

    Future plugins register via entry points or explicit ``PluginLoader.register``.
    Dynamic network downloads are intentionally unsupported.
    """

    @property
    def name(self) -> str: ...

    def load(self) -> list[Agent]: ...


class PluginLoader:
    """Load agents from registered plugins / import paths."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._plugins: dict[str, IAgentPlugin] = {}

    def register(self, plugin: IAgentPlugin) -> None:
        with self._lock:
            if not isinstance(plugin, IAgentPlugin) and not (
                hasattr(plugin, "name") and callable(getattr(plugin, "load", None))
            ):
                raise PluginError("plugin must implement IAgentPlugin")
            name = plugin.name
            if not name:
                raise PluginError("plugin name required")
            self._plugins[name] = plugin

    def unregister(self, name: str) -> None:
        with self._lock:
            self._plugins.pop(name, None)

    def list_plugins(self) -> list[str]:
        with self._lock:
            return sorted(self._plugins.keys())

    def load_all(self) -> list[Agent]:
        with self._lock:
            plugins = list(self._plugins.values())
        agents: list[Agent] = []
        for plugin in plugins:
            try:
                loaded = plugin.load()
            except Exception as exc:
                raise PluginError(f"plugin {plugin.name} failed: {exc}") from exc
            if not isinstance(loaded, list):
                raise PluginError(f"plugin {plugin.name} must return list[Agent]")
            agents.extend(loaded)
        return agents

    def load_module(self, module_path: str, *, attr: str = "plugin") -> IAgentPlugin:
        """Import ``module_path`` and register ``attr`` as plugin.

        Example: ``loader.load_module("my_pkg.agents", attr="plugin")``
        """
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginError(f"cannot import plugin module: {module_path}") from exc
        plugin = getattr(mod, attr, None)
        if plugin is None:
            raise PluginError(f"module {module_path} has no attribute {attr}")
        if callable(plugin) and not hasattr(plugin, "load"):
            plugin = plugin()
        self.register(plugin)
        return plugin


class CallablePlugin:
    """Adapter: wrap a zero-arg callable returning list[Agent]."""

    def __init__(self, name: str, factory: object) -> None:
        self._name = name
        self._factory = factory

    @property
    def name(self) -> str:
        return self._name

    def load(self) -> list[Agent]:
        result = self._factory()  # type: ignore[operator]
        if not isinstance(result, list):
            raise PluginError(f"callable plugin {self._name} must return list[Agent]")
        return result
