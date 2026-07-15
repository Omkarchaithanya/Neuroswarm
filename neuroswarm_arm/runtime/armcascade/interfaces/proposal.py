"""ASCR strategy / engine protocols."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .types import (
    AcceptanceDecision,
    AcceptanceSignals,
    ASCRInitContext,
    Classification,
    EscalationEdge,
    EscalationGraph,
    EscalationState,
    PolicyDecision,
    Proposal,
    ProposalRequest,
    ThresholdInputs,
    ThresholdSet,
    VerifyRequest,
    VerifyResult,
)

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.interfaces.types import (
        ExecutionPlan,
        InferenceRequest,
    )


class ProposalStrategy(ABC):
    name: str = "base"

    @abstractmethod
    async def initialize(self, ctx: ASCRInitContext) -> None:
        raise NotImplementedError

    async def warmup(self) -> None:
        return None

    @abstractmethod
    async def propose(self, req: ProposalRequest) -> Proposal:
        raise NotImplementedError

    def estimate_confidence(self, proposal: Proposal) -> float:
        return float(proposal.confidence)

    async def shutdown(self) -> None:
        return None


class VerifierStrategy(ABC):
    name: str = "base"

    @abstractmethod
    async def initialize(self, ctx: ASCRInitContext) -> None:
        raise NotImplementedError

    async def warmup(self) -> None:
        return None

    @abstractmethod
    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        raise NotImplementedError

    async def shutdown(self) -> None:
        return None


class RequestClassifier(ABC):
    @abstractmethod
    def classify(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan | None = None,
    ) -> Classification:
        raise NotImplementedError


class ConfidenceEngine(ABC):
    @abstractmethod
    def fuse(self, signals: AcceptanceSignals) -> float:
        raise NotImplementedError


class AcceptanceEngine(ABC):
    @abstractmethod
    def decide(self, signals: AcceptanceSignals) -> AcceptanceDecision:
        raise NotImplementedError


class ThresholdEngine(ABC):
    @abstractmethod
    def compute(self, inputs: ThresholdInputs) -> ThresholdSet:
        raise NotImplementedError


class EscalationEngine(ABC):
    @abstractmethod
    def next(self, graph: EscalationGraph, state: EscalationState) -> EscalationEdge | None:
        raise NotImplementedError


class CascadePolicyEngine(ABC):
    @abstractmethod
    def decide(
        self,
        classification: Classification,
        plan: ExecutionPlan | None = None,
        telemetry: dict | None = None,
    ) -> PolicyDecision:
        raise NotImplementedError
