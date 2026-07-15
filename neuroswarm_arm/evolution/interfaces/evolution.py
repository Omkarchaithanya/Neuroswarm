"""Evolution / policy lineage port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

from neuroswarm_arm.evolution.models.policy import RuntimePolicy


@dataclass(frozen=True, slots=True)
class PolicyLineage:
    policy_id: str
    version: str
    parent_id: str | None
    content_hash: str
    okf_path: str | None = None
    git_ref: str | None = None
    release_tag: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class EvolutionEngine(ABC):
    @abstractmethod
    def record(self, policy: RuntimePolicy, *, okf_path: str | None = None) -> PolicyLineage:
        raise NotImplementedError

    @abstractmethod
    def lineage(self, policy_id: str) -> list[PolicyLineage]:
        raise NotImplementedError

    @abstractmethod
    def graph(self) -> Mapping[str, list[str]]:
        """parent_id -> [child_ids]."""
        raise NotImplementedError
