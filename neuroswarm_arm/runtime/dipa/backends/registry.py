"""DIPA inference backend registry."""

from __future__ import annotations

from neuroswarm_arm.runtime.dipa.interfaces.backend import InferenceBackend
from neuroswarm_arm.runtime.dipa.interfaces.types import HealthStatus


class BackendRegistry:
    """Register and look up :class:`InferenceBackend` plugins by name."""

    def __init__(self) -> None:
        self._plugins: dict[str, InferenceBackend] = {}

    def register(self, backend: InferenceBackend) -> None:
        """Register *backend* under ``backend.name`` (replaces existing)."""
        self._plugins[backend.name] = backend

    def get(
        self, name: str, default: InferenceBackend | None = None
    ) -> InferenceBackend | None:
        """Return backend *name*, or *default* when missing.

        Raises:
            KeyError: If missing and *default* is omitted (``default`` is
            the sentinel ``...`` via explicit require path — use
            :meth:`require` when a backend must exist).
        """
        if name in self._plugins:
            return self._plugins[name]
        if default is not None:
            return default
        return None

    def require(self, name: str) -> InferenceBackend:
        backend = self.get(name)
        if backend is None:
            raise KeyError(f"backend not registered: {name}")
        return backend

    def list(self) -> list[str]:
        """Return sorted registered backend names."""
        return sorted(self._plugins)

    def all(self) -> list[InferenceBackend]:
        """Return all registered backend instances."""
        return [self._plugins[name] for name in self.list()]

    async def health_all(self) -> dict[str, HealthStatus]:
        """Probe health for every registered backend."""
        out: dict[str, HealthStatus] = {}
        for name, backend in self._plugins.items():
            out[name] = await backend.health()
        return out
