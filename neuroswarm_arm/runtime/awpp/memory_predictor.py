"""AWPP connector — speculative prefetch hints from Cognitive Memory Runtime."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.awpp.actions import AWPPAction, WarmTarget, WarmTargetKind
from neuroswarm_arm.runtime.awpp.interfaces import IPredictor, Prediction
from neuroswarm_arm.runtime.awpp.state import AWPPState
from neuroswarm_arm.runtime.awpp.uncertainty import shannon_entropy


class MemoryPrefetchPredictor(IPredictor):
    """Maps ``NeuroMemory.predict_next`` → AWPP prewarm Prediction."""

    name = "memory_prefetch"

    def __init__(self, memory: Any | None = None) -> None:
        self.memory = memory

    def predict(self, state: AWPPState) -> Prediction:
        neuro = self.memory
        if neuro is not None and hasattr(neuro, "neuro"):
            neuro = neuro.neuro
        if neuro is None or not hasattr(neuro, "predict_next"):
            return Prediction(
                action=AWPPAction(skip=True),
                confidence=0.0,
                entropy=1.0,
                uncertainty=1.0,
                policy_id=self.name,
            )
        owner = str(state.agent_id or "default")
        context = str(state.metadata.get("prompt_excerpt") or state.current_node or "")
        try:
            result = neuro.predict_next(owner, context=context)
        except Exception:
            return Prediction(
                action=AWPPAction(skip=True),
                confidence=0.0,
                entropy=1.0,
                uncertainty=1.0,
                policy_id=self.name,
            )
        conf = float(result.confidence or 0.0)
        targets: list[WarmTarget] = []
        if result.next_tool:
            targets.append(WarmTarget(WarmTargetKind.TOOL, result.next_tool, conf))
        if result.next_model:
            targets.append(WarmTarget(WarmTargetKind.MODEL, result.next_model, conf * 0.9))
        if result.next_memory:
            targets.append(WarmTarget(WarmTargetKind.MEMORY, result.next_memory, conf * 0.8))
        action = AWPPAction(
            targets=targets,
            next_tool=result.next_tool,
            next_model=result.next_model,
            memory_keys=[result.next_memory] if result.next_memory else [],
            skip=conf < 0.2 or not targets,
        )
        p = max(1e-6, min(1.0 - 1e-6, conf))
        ent = float(shannon_entropy([p, 1.0 - p]))
        return Prediction(
            action=action,
            confidence=conf,
            entropy=ent,
            uncertainty=1.0 - conf,
            policy_id=self.name,
            metadata={
                "source": "neuro_memory",
                "next_workflow": result.next_workflow,
                "next_planner": result.next_planner,
                "scores": result.scores,
            },
        )
