"""Frequency-based warm policy — most common model/tool per agent."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from neuroswarm_arm.runtime.awpp.actions import AWPPAction, WarmTarget, WarmTargetKind
from neuroswarm_arm.runtime.awpp.confidence import clamp01, from_max_prob, sample_size_factor
from neuroswarm_arm.runtime.awpp.interfaces import IPolicy, Prediction
from neuroswarm_arm.runtime.awpp.observation import Observation
from neuroswarm_arm.runtime.awpp.state import AWPPState
from neuroswarm_arm.runtime.awpp.uncertainty import shannon_entropy


class FrequencyPolicy(IPolicy):
    """Predict next warm targets from historical frequency counts."""

    policy_id = "frequency"
    version = "1"

    def __init__(self, *, min_observations: int = 3) -> None:
        self.min_observations = min_observations
        self._models: dict[str, Counter[str]] = defaultdict(Counter)
        self._tools: dict[str, Counter[str]] = defaultdict(Counter)
        self._totals: Counter[str] = Counter()

    def act(self, state: AWPPState, *, deterministic: bool = True) -> Prediction:
        agent = str(state.agent_id or "default")
        n = int(self._totals[agent])
        if n < self.min_observations:
            return Prediction(
                action=AWPPAction(skip=True),
                confidence=0.0,
                entropy=1.0,
                uncertainty=1.0,
                policy_id=self.policy_id,
                policy_version=self.version,
                metadata={"reason": "insufficient_history", "n": n},
            )
        model_counts = self._models[agent]
        tool_counts = self._tools[agent]
        next_model = model_counts.most_common(1)[0][0] if model_counts else ""
        next_tool = tool_counts.most_common(1)[0][0] if tool_counts else ""
        model_total = sum(model_counts.values()) or 1
        tool_total = sum(tool_counts.values()) or 1
        model_probs = [c / model_total for _, c in model_counts.most_common(5)]
        tool_probs = [c / tool_total for _, c in tool_counts.most_common(5)]
        conf = clamp01(
            0.5 * from_max_prob(model_probs or [0.0])
            + 0.3 * from_max_prob(tool_probs or [0.0])
            + 0.2 * sample_size_factor(n)
        )
        targets: list[WarmTarget] = []
        if next_model:
            targets.append(WarmTarget(WarmTargetKind.MODEL, next_model, conf))
        if next_tool:
            targets.append(WarmTarget(WarmTargetKind.TOOL, next_tool, conf * 0.9))
        action = AWPPAction(
            targets=targets,
            next_model=next_model,
            next_tool=next_tool,
            skip=not targets or conf < 0.15,
        )
        p = max(1e-6, min(1.0 - 1e-6, conf))
        return Prediction(
            action=action,
            confidence=conf,
            entropy=float(shannon_entropy([p, 1.0 - p])),
            uncertainty=1.0 - conf,
            policy_id=self.policy_id,
            policy_version=self.version,
            metadata={"n": n, "deterministic": deterministic},
        )

    def update(self, observation: Observation) -> None:
        agent = str(observation.agent_id or "default")
        self._totals[agent] += 1
        if observation.model:
            self._models[agent][observation.model] += 1
        if observation.tool:
            self._tools[agent][observation.tool] += 1

    def train_step(self, batch: list[Mapping[str, Any]]) -> dict[str, float]:
        for row in batch:
            self.update(Observation.from_dict(row))
        return {"updated": float(len(batch))}

    def evaluate(self, batch: list[Mapping[str, Any]]) -> dict[str, float]:
        if not batch:
            return {"accuracy": 0.0, "n": 0.0}
        hits = 0
        for row in batch:
            state = AWPPState(
                agent_id=str(row.get("agent_id") or "default"),
                metadata={"prompt_excerpt": str(row.get("prompt_hash") or "")},
            )
            pred = self.act(state)
            actual_model = str(row.get("model") or "")
            if pred.action.next_model and pred.action.next_model == actual_model:
                hits += 1
        return {"accuracy": hits / max(1, len(batch)), "n": float(len(batch))}

    def save(self, path: str) -> None:
        payload = {
            "policy_id": self.policy_id,
            "version": self.version,
            "models": {k: dict(v) for k, v in self._models.items()},
            "tools": {k: dict(v) for k, v in self._tools.items()},
            "totals": dict(self._totals),
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._models = defaultdict(Counter, {k: Counter(v) for k, v in dict(data.get("models") or {}).items()})
        self._tools = defaultdict(Counter, {k: Counter(v) for k, v in dict(data.get("tools") or {}).items()})
        self._totals = Counter(dict(data.get("totals") or {}))
