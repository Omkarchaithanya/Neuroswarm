"""ASCR connector — memory_needed escalation invokes ACR, not raw Mem0."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.acr.connectors import escalate_memory_needed
from neuroswarm_arm.runtime.acr.kernel import AdaptiveContextRuntime


class ASCRMemoryConnector:
    """Layer 5 ASCR → Layer 4 ACR. Connectors not ownership (ADR style)."""

    def __init__(self, acr: AdaptiveContextRuntime | None = None) -> None:
        self.acr = acr

    def on_memory_needed(
        self,
        query: str,
        *,
        owner: str = "default",
        agent_role: str = "architect",
        extra_budget: int = 800,
    ) -> str:
        return escalate_memory_needed(
            self.acr,
            query=query,
            owner=owner,
            agent_role=agent_role,
            extra_budget=extra_budget,
        )

    def bind(self, acr: AdaptiveContextRuntime) -> None:
        self.acr = acr
