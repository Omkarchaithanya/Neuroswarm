"""RTG public contracts — peer layer ports and Protocols."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Protocol, runtime_checkable

from .models import BudgetEnvelope, Decision, SessionState, TelemetryFrame


class ISensor(ABC):
    name: str = "sensor"

    @abstractmethod
    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        raise NotImplementedError


class IEstimator(ABC):
    name: str = "estimator"

    @abstractmethod
    def estimate(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        raise NotImplementedError


class IPolicy(ABC):
    policy_id: str = "policy"
    layer: str = "L1"

    @abstractmethod
    def decide(self, frame: TelemetryFrame, state: SessionState) -> Decision | None:
        """Return a Decision or None to defer to a lower-priority policy."""
        raise NotImplementedError


class IBudgetAllocator(ABC):
    @abstractmethod
    def initial_budget(self, frame: TelemetryFrame) -> BudgetEnvelope:
        raise NotImplementedError

    @abstractmethod
    def next_chunk(self, state: SessionState) -> int:
        raise NotImplementedError


class IStreamingController(ABC):
    @abstractmethod
    def on_admit(self, frame: TelemetryFrame) -> SessionState:
        raise NotImplementedError

    @abstractmethod
    def on_chunk(self, session_id: str, chunk_text: str, **kwargs: Any) -> Decision:
        raise NotImplementedError

    @abstractmethod
    def on_complete(self, session_id: str, final_text: str = "") -> Decision:
        raise NotImplementedError


@runtime_checkable
class SupportsPressureSnapshot(Protocol):
    def pressure_snapshot(self) -> Mapping[str, Any]: ...


@runtime_checkable
class SupportsToolConfidence(Protocol):
    def route(self, query: str) -> list[Any]: ...
