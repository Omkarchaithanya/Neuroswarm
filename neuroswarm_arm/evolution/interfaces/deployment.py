"""Deployment controller — shadow / canary / blue-green / rollback."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from neuroswarm_arm.evolution.models.experiment import CandidatePolicy
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


class DeploymentMode(str, Enum):
    SHADOW = "shadow"
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    PERCENTAGE = "percentage"
    FULL = "full"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class DeploymentResult:
    success: bool
    mode: DeploymentMode
    active_policy_id: str | None
    canary_percent: float = 0.0
    message: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)


class DeploymentController(ABC):
    @abstractmethod
    def deploy_shadow(self, candidate: CandidatePolicy) -> DeploymentResult:
        raise NotImplementedError

    @abstractmethod
    def deploy_canary(self, candidate: CandidatePolicy, *, percent: float = 10.0) -> DeploymentResult:
        raise NotImplementedError

    @abstractmethod
    def promote(self, candidate: CandidatePolicy) -> DeploymentResult:
        raise NotImplementedError

    @abstractmethod
    def rollback(self, *, to_policy: RuntimePolicy | None = None) -> DeploymentResult:
        raise NotImplementedError

    @abstractmethod
    def active_policy(self) -> RuntimePolicy | None:
        raise NotImplementedError

    def resolve_for_request(self, *, agent_id: str = "") -> RuntimePolicy | None:
        """Sticky canary: hash agent_id into canary vs active."""
        return self.active_policy()
