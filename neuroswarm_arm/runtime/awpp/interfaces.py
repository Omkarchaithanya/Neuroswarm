"""AWPP public contracts — peer layer ports and Protocols."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from .actions import AWPPAction
from .observation import Observation
from .state import AWPPState


class FeatureStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class Prediction:
    """Prediction envelope with mandatory uncertainty."""

    action: AWPPAction
    confidence: float
    entropy: float
    uncertainty: float
    policy_id: str = ""
    policy_version: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def should_prewarm(self) -> bool:
        return (not self.action.skip) and self.confidence > 0.0


@dataclass(slots=True)
class PrewarmBudget:
    max_concurrent: int = 4
    max_memory_bytes: int = 2 * 1024**3
    max_cpu_fraction: float = 0.35
    timeout_s: float = 5.0
    rate_limit_per_s: float = 20.0
    numa_node: int | None = None


@dataclass(slots=True)
class WarmResult:
    target_kind: str
    target_key: str
    success: bool
    latency_ms: float = 0.0
    bytes_touched: int = 0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class IPredictor(ABC):
    name: str = "predictor"

    @abstractmethod
    def predict(self, state: AWPPState) -> Prediction:
        raise NotImplementedError

    def update(self, observation: Observation) -> None:
        return None


class IPolicy(ABC):
    policy_id: str = "policy"
    version: str = "0"

    @abstractmethod
    def act(self, state: AWPPState, *, deterministic: bool = True) -> Prediction:
        raise NotImplementedError

    @abstractmethod
    def train_step(self, batch: list[Mapping[str, Any]]) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, batch: list[Mapping[str, Any]]) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def save(self, path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self, path: str) -> None:
        raise NotImplementedError


class IWarmer(ABC):
    kind: str = "warmer"

    @abstractmethod
    async def warm(self, key: str, *, metadata: Mapping[str, Any] | None = None) -> WarmResult:
        raise NotImplementedError

    @abstractmethod
    def is_warm(self, key: str) -> bool:
        raise NotImplementedError


class IMTEProvider(ABC):
    """Future Memory Tagging Extension — UNAVAILABLE on Axion today."""

    @abstractmethod
    def status(self) -> FeatureStatus:
        raise NotImplementedError

    @abstractmethod
    def tag_pages(self, pages: list[str], agent_id: str) -> bool:
        raise NotImplementedError


class ICXLProvider(ABC):
    """Future CXL memory pool — UNAVAILABLE on Axion today."""

    @abstractmethod
    def status(self) -> FeatureStatus:
        raise NotImplementedError

    @abstractmethod
    def prefetch(self, keys: list[str]) -> int:
        raise NotImplementedError


@runtime_checkable
class SupportsMem0(Protocol):
    def add(self, agent_id: str, fact: str, metadata: dict[str, str] | None = None) -> None: ...

    def search(self, agent_id: str, query: str, limit: int = 5) -> list[str]: ...

    def get_recent_workflow(self, agent_id: str, limit: int = 20) -> list[dict[str, Any]]: ...


@runtime_checkable
class SupportsOKF(Protocol):
    def load_index(self) -> Any: ...

    def load_topic(self, relative_path: str) -> Any: ...


@runtime_checkable
class SupportsKVPressure(Protocol):
    def pressure_snapshot(self) -> Mapping[str, Any]: ...
