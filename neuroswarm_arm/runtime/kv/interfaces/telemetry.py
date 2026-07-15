"""IKVTelemetry contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IKVTelemetry(ABC):
    """KV-specific metrics sink."""

    @abstractmethod
    def inc(self, name: str, value: float = 1.0) -> None:
        raise NotImplementedError

    @abstractmethod
    def set(self, name: str, value: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def observe(self, name: str, value: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def export_prometheus(self) -> str:
        raise NotImplementedError

    def describe(self, name: str, metric_type: str, help_text: str) -> None:
        _ = (name, metric_type, help_text)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.snapshot())
