"""Capability discovery — backend KV feature matrix. Never assume cross-model reuse."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class IBackendKVCapability(Protocol):
    """Every inference backend must expose these gates."""

    @property
    def backend_id(self) -> str: ...

    def supports_prefix_reuse(self) -> bool: ...

    def supports_shared_kv(self) -> bool: ...

    def supports_paged_kv(self) -> bool: ...

    def supports_speculative_kv(self) -> bool: ...

    def supports_cross_session_reuse(self) -> bool: ...

    def supports_cross_model_reuse(self) -> bool: ...


@dataclass(frozen=True)
class CapabilityFlags:
    prefix_reuse: bool = False
    shared_kv: bool = False
    paged_kv: bool = False
    speculative_kv: bool = False
    cross_session_reuse: bool = False
    cross_model_reuse: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "supports_prefix_reuse": self.prefix_reuse,
            "supports_shared_kv": self.shared_kv,
            "supports_paged_kv": self.paged_kv,
            "supports_speculative_kv": self.speculative_kv,
            "supports_cross_session_reuse": self.cross_session_reuse,
            "supports_cross_model_reuse": self.cross_model_reuse,
        }

    @classmethod
    def from_adapter(cls, adapter: IBackendKVCapability) -> CapabilityFlags:
        return cls(
            prefix_reuse=bool(adapter.supports_prefix_reuse()),
            shared_kv=bool(adapter.supports_shared_kv()),
            paged_kv=bool(adapter.supports_paged_kv()),
            speculative_kv=bool(adapter.supports_speculative_kv()),
            cross_session_reuse=bool(adapter.supports_cross_session_reuse()),
            cross_model_reuse=bool(adapter.supports_cross_model_reuse()),
        )


@dataclass
class BackendCapabilityAdapter:
    """Concrete adapter base — override flags per engine."""

    backend_id: str
    flags: CapabilityFlags = field(default_factory=CapabilityFlags)

    def supports_prefix_reuse(self) -> bool:
        return self.flags.prefix_reuse

    def supports_shared_kv(self) -> bool:
        return self.flags.shared_kv

    def supports_paged_kv(self) -> bool:
        return self.flags.paged_kv

    def supports_speculative_kv(self) -> bool:
        return self.flags.speculative_kv

    def supports_cross_session_reuse(self) -> bool:
        return self.flags.cross_session_reuse

    def supports_cross_model_reuse(self) -> bool:
        return self.flags.cross_model_reuse


class CapabilityRegistry:
    """Discovers and stores backend capabilities. MAKS adapts automatically."""

    def __init__(self) -> None:
        self._adapters: dict[str, IBackendKVCapability] = {}
        self._lock = RLock()
        self._default = BackendCapabilityAdapter(
            backend_id="opaque",
            flags=CapabilityFlags(
                prefix_reuse=True,
                shared_kv=True,
                paged_kv=False,
                speculative_kv=False,
                cross_session_reuse=True,
                cross_model_reuse=False,
            ),
        )

    def register(self, adapter: IBackendKVCapability) -> None:
        with self._lock:
            self._adapters[adapter.backend_id] = adapter

    def get(self, backend_id: str) -> IBackendKVCapability:
        with self._lock:
            return self._adapters.get(backend_id, self._default)

    def flags(self, backend_id: str) -> CapabilityFlags:
        return CapabilityFlags.from_adapter(self.get(backend_id))

    def matrix(self) -> dict[str, dict[str, bool]]:
        with self._lock:
            out = {bid: CapabilityFlags.from_adapter(a).as_dict() for bid, a in self._adapters.items()}
            out.setdefault("opaque", CapabilityFlags.from_adapter(self._default).as_dict())
            return out

    def can_reuse(
        self,
        backend_id: str,
        *,
        cross_model: bool = False,
        cross_session: bool = False,
        require_paged: bool = False,
    ) -> bool:
        f = self.flags(backend_id)
        if cross_model and not f.cross_model_reuse:
            return False
        if cross_session and not f.cross_session_reuse:
            return False
        if require_paged and not f.paged_kv:
            return False
        return True

    def prefer_mode(self, backend_id: str) -> str:
        """Return allocation mode: paged | prefix | opaque."""
        f = self.flags(backend_id)
        if f.paged_kv:
            return "paged"
        if f.prefix_reuse:
            return "prefix"
        return "opaque"

    def list_backends(self) -> list[str]:
        with self._lock:
            return sorted(self._adapters.keys())


def build_default_capability_registry() -> CapabilityRegistry:
    """Register Axion-honest defaults for known engines."""
    from .engines import build_default_engines

    reg = CapabilityRegistry()
    for adapter in build_default_engines():
        reg.register(adapter)
    return reg
