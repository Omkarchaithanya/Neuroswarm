"""Lifecycle contracts for DIPA control plane."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Mapping


class LifecyclePhase(str, Enum):
    CREATED = "created"
    DETECTING = "detecting"
    AFFINITY = "affinity"
    BACKENDS = "backends"
    MODELS = "models"
    WARMUP = "warmup"
    READY = "ready"
    DRAINING = "draining"
    STOPPED = "stopped"
    FAILED = "failed"


class ILifecycle(ABC):
    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def drain(self, timeout_s: float = 30.0) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def phase(self) -> LifecyclePhase:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> Mapping[str, Any]:
        raise NotImplementedError
