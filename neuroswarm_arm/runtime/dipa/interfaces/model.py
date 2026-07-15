"""Model routing contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import ExecutionPlan, InferenceRequest, ModelCandidate, RouteScore


class IModelRouter(ABC):
    @abstractmethod
    def candidates(self) -> list[ModelCandidate]:
        raise NotImplementedError

    @abstractmethod
    def route(self, req: InferenceRequest, plan: ExecutionPlan) -> RouteScore:
        raise NotImplementedError
