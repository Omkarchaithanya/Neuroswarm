"""HAOE interface contracts (ABCs).

Higher layers depend on these contracts; concrete implementations live under
scheduling/, execution/, topology/, telemetry/. This mirrors the KV runtime's
interfaces/ package and prevents circular imports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Mapping, Sequence

from .types import (
    AffinityHint,
    CorrelationIds,
    ExecutorKind,
    FeatureStatus,
    PoolKind,
    PriorityClass,
    ResourceEstimate,
    TaskState,
)


class IScheduler(ABC):
    """Priority-aware admission control into worker pools."""

    @abstractmethod
    def submit(
        self,
        task_id: str,
        *,
        priority: PriorityClass = PriorityClass.NORMAL,
        pool: PoolKind = PoolKind.BACKGROUND,
        estimate: ResourceEstimate | None = None,
        affinity: AffinityHint | None = None,
        payload: Any = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def poll(self, worker_id: str, pool: PoolKind) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def steal(self, thief_id: str, pool: PoolKind) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def depth(self, pool: PoolKind | None = None) -> int:
        raise NotImplementedError


class IExecutor(ABC):
    """Runs a single ready task on a chosen backend."""

    kind: ExecutorKind

    @abstractmethod
    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def shutdown(self, wait: bool = True) -> None:
        raise NotImplementedError


class INativeExecutor(IExecutor):
    """Extension point for a future Rust / C HAOE scheduler."""

    kind = ExecutorKind.NATIVE


class ITopologyService(ABC):
    """Hardware topology abstraction — never hardcodes Axion or Graviton."""

    @abstractmethod
    def cpu_count(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def core_ids(self) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def fast_cores(self) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def efficiency_cores(self) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def numa_nodes(self) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def feature(self, name: str) -> FeatureStatus:
        raise NotImplementedError

    @abstractmethod
    def features(self) -> Mapping[str, FeatureStatus]:
        raise NotImplementedError

    @abstractmethod
    def cache_hierarchy(self) -> Mapping[str, Any]:
        raise NotImplementedError


class IAffinityProvider(ABC):
    """Best-effort CPU affinity (taskset / sched_setaffinity / no-op)."""

    @abstractmethod
    def bind(self, cores: Sequence[int]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def unbind(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def current(self) -> list[int]:
        raise NotImplementedError


class IMetricsExporter(ABC):
    @abstractmethod
    def inc(self, name: str, value: float = 1.0) -> None:
        raise NotImplementedError

    @abstractmethod
    def set(self, name: str, value: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def observe(self, name: str, value: float) -> None:
        raise NotImplementedError


class IEventBus(ABC):
    @abstractmethod
    def publish(self, topic: str, event: Mapping[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[Mapping[str, Any]], None]) -> None:
        raise NotImplementedError

    @abstractmethod
    def unsubscribe(self, topic: str, handler: Callable[[Mapping[str, Any]], None]) -> None:
        raise NotImplementedError


class IMemoryProvider(ABC):
    """Memory policy / future MTE. Software path today."""

    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def available_bytes(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def pressure(self) -> float:
        raise NotImplementedError


class ICPUProvider(ABC):
    @abstractmethod
    def core_ids(self) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def logical_count(self) -> int:
        raise NotImplementedError


class IKVPressureProvider(ABC):
    """Thin protocol so HAOE can read KV pressure without importing KV types."""

    @abstractmethod
    def pressure_snapshot(self) -> Mapping[str, Any]:
        raise NotImplementedError


class ISchedulingProvider(ABC):
    @abstractmethod
    def pool_size(self, pool: PoolKind) -> int:
        raise NotImplementedError

    @abstractmethod
    def steal_enabled(self) -> bool:
        raise NotImplementedError


class ITaskHandle(ABC):
    """Handle returned to callers for observation / cancellation."""

    @property
    @abstractmethod
    def task_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def state(self) -> TaskState:
        raise NotImplementedError

    @property
    @abstractmethod
    def ids(self) -> CorrelationIds:
        raise NotImplementedError

    @abstractmethod
    def result(self, timeout: float | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    def cancel(self) -> bool:
        raise NotImplementedError
