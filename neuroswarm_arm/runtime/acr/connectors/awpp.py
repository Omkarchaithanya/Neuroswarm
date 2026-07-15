"""AWPP predictor that prefers ACR plan hints, falls back to NeuroMemory."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.acr.connectors import awpp_prefetch_hints
from neuroswarm_arm.runtime.awpp.actions import AWPPAction, WarmTarget, WarmTargetKind
from neuroswarm_arm.runtime.awpp.interfaces import IPredictor, Prediction
from neuroswarm_arm.runtime.awpp.memory_predictor import MemoryPrefetchPredictor
from neuroswarm_arm.runtime.awpp.state import AWPPState
from neuroswarm_arm.runtime.awpp.uncertainty import shannon_entropy


class ACRPrefetchPredictor(IPredictor):
    """AWPP Layer-4 peer consumes ACR Context OS planning signals."""

    name = "acr_prefetch"

    def __init__(self, acr: Any | None = None, memory: Any | None = None) -> None:
        self.acr = acr
        self._fallback = MemoryPrefetchPredictor(memory=memory)

    def predict(self, state: AWPPState) -> Prediction:
        if self.acr is not None and getattr(self.acr, "enabled", False):
            query = str(state.metadata.get("prompt_excerpt") or state.current_node or "")
            owner = str(state.agent_id or "default")
            role = str(state.metadata.get("agent_role") or "architect")
            hints = awpp_prefetch_hints(self.acr, query=query, owner=owner, agent_role=role)
            tools = list(hints.get("predicted_tools") or [])
            targets: list[WarmTarget] = []
            conf = 0.55 if tools or hints.get("steps") else 0.2
            for t in tools[:3]:
                targets.append(WarmTarget(WarmTargetKind.TOOL, t, conf))
            for ns in list(hints.get("namespaces") or [])[:2]:
                targets.append(WarmTarget(WarmTargetKind.MEMORY, ns, conf * 0.8))
            if targets:
                p = max(1e-6, min(1.0 - 1e-6, conf))
                return Prediction(
                    action=AWPPAction(
                        targets=targets,
                        next_tool=tools[0] if tools else "",
                        memory_keys=[t.key for t in targets if t.kind == WarmTargetKind.MEMORY],
                        skip=False,
                    ),
                    confidence=conf,
                    entropy=float(shannon_entropy([p, 1.0 - p])),
                    uncertainty=1.0 - conf,
                    policy_id=self.name,
                    metadata={"source": "acr", "intent": hints.get("intent"), "steps": hints.get("steps")},
                )
        return self._fallback.predict(state)
