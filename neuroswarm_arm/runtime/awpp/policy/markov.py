"""Markov chain warm policy over model/tool sequences."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from neuroswarm_arm.runtime.awpp.actions import AWPPAction, WarmTarget, WarmTargetKind
from neuroswarm_arm.runtime.awpp.confidence import clamp01, from_max_prob, sample_size_factor
from neuroswarm_arm.runtime.awpp.interfaces import IPolicy, Prediction
from neuroswarm_arm.runtime.awpp.observation import Observation
from neuroswarm_arm.runtime.awpp.policy.frequency import FrequencyPolicy
from neuroswarm_arm.runtime.awpp.state import AWPPState
from neuroswarm_arm.runtime.awpp.uncertainty import shannon_entropy


class MarkovPolicy(IPolicy):
    """First-order Markov over (last_model → next_model) and (last_tool → next_tool)."""

    policy_id = "markov"
    version = "1"

    def __init__(self, *, min_observations: int = 3) -> None:
        self.min_observations = min_observations
        self._model_trans: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        self._tool_trans: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        self._last_model: dict[str, str] = {}
        self._last_tool: dict[str, str] = {}
        self._fallback = FrequencyPolicy(min_observations=min_observations)
        self._totals: Counter[str] = Counter()

    def act(self, state: AWPPState, *, deterministic: bool = True) -> Prediction:
        agent = str(state.agent_id or "default")
        n = int(self._totals[agent])
        if n < self.min_observations:
            return self._fallback.act(state, deterministic=deterministic)

        last_model = str(
            state.metadata.get("last_model")
            or self._last_model.get(agent)
            or ""
        )
        last_tool = str(
            state.metadata.get("last_tool")
            or (state.metadata.get("last_tools") or [None])[-1]
            or self._last_tool.get(agent)
            or ""
        )
        if isinstance(state.metadata.get("last_tools"), list) and state.metadata["last_tools"]:
            last_tool = str(state.metadata["last_tools"][-1] or last_tool)

        next_model, model_probs = self._transition(
            self._model_trans[agent], last_model
        )
        next_tool, tool_probs = self._transition(self._tool_trans[agent], last_tool)

        if not next_model and not next_tool:
            return self._fallback.act(state, deterministic=deterministic)

        conf = clamp01(
            0.45 * from_max_prob(model_probs or [0.0])
            + 0.35 * from_max_prob(tool_probs or [0.0])
            + 0.2 * sample_size_factor(n)
        )
        targets: list[WarmTarget] = []
        if next_model:
            targets.append(WarmTarget(WarmTargetKind.MODEL, next_model, conf))
        if next_tool:
            targets.append(WarmTarget(WarmTargetKind.TOOL, next_tool, conf * 0.9))
        # Pin memory namespace from prompt excerpt when present
        excerpt = str(state.metadata.get("prompt_excerpt") or "")[:64]
        if excerpt:
            targets.append(WarmTarget(WarmTargetKind.MEMORY, excerpt, conf * 0.6))

        action = AWPPAction(
            targets=targets,
            next_model=next_model,
            next_tool=next_tool,
            memory_keys=[excerpt] if excerpt else [],
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
            metadata={
                "n": n,
                "last_model": last_model,
                "last_tool": last_tool,
                "deterministic": deterministic,
            },
        )

    def _transition(
        self, table: dict[str, Counter[str]], key: str
    ) -> tuple[str, list[float]]:
        counts = table.get(key) or Counter()
        if not counts and table:
            # cold start for this key — use global marginal
            merged: Counter[str] = Counter()
            for c in table.values():
                merged.update(c)
            counts = merged
        if not counts:
            return "", []
        total = sum(counts.values()) or 1
        ordered = counts.most_common()
        probs = [c / total for _, c in ordered[:5]]
        return ordered[0][0], probs

    def update(self, observation: Observation) -> None:
        agent = str(observation.agent_id or "default")
        self._totals[agent] += 1
        self._fallback.update(observation)
        prev_model = self._last_model.get(agent, "")
        prev_tool = self._last_tool.get(agent, "")
        if observation.model:
            if prev_model:
                self._model_trans[agent][prev_model][observation.model] += 1
            self._last_model[agent] = observation.model
        if observation.tool:
            if prev_tool:
                self._tool_trans[agent][prev_tool][observation.tool] += 1
            self._last_tool[agent] = observation.tool

    def record_tools(self, tool_ids: list[str], *, agent_id: str = "default") -> None:
        """One-line warmer hook: chain routed tool ids into Markov transitions."""
        agent = str(agent_id or "default")
        for tid in tool_ids or []:
            tid_s = str(tid or "")
            if not tid_s:
                continue
            prev = self._last_tool.get(agent, "")
            if prev:
                self._tool_trans[agent][prev][tid_s] += 1
            self._last_tool[agent] = tid_s
            self._totals[agent] += 1

    def train_step(self, batch: list[Mapping[str, Any]]) -> dict[str, float]:
        for row in batch:
            self.update(Observation.from_dict(row))
        return {"updated": float(len(batch))}

    def evaluate(self, batch: list[Mapping[str, Any]]) -> dict[str, float]:
        return self._fallback.evaluate(batch)

    def save(self, path: str) -> None:
        payload = {
            "policy_id": self.policy_id,
            "version": self.version,
            "model_trans": {
                a: {k: dict(v) for k, v in d.items()}
                for a, d in self._model_trans.items()
            },
            "tool_trans": {
                a: {k: dict(v) for k, v in d.items()}
                for a, d in self._tool_trans.items()
            },
            "last_model": dict(self._last_model),
            "last_tool": dict(self._last_tool),
            "totals": dict(self._totals),
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._fallback.save(str(Path(path).with_suffix(".frequency.json")))

    def load(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._model_trans = defaultdict(lambda: defaultdict(Counter))
        for a, d in dict(data.get("model_trans") or {}).items():
            for k, v in d.items():
                self._model_trans[a][k] = Counter(v)
        self._tool_trans = defaultdict(lambda: defaultdict(Counter))
        for a, d in dict(data.get("tool_trans") or {}).items():
            for k, v in d.items():
                self._tool_trans[a][k] = Counter(v)
        self._last_model = {str(k): str(v) for k, v in dict(data.get("last_model") or {}).items()}
        self._last_tool = {str(k): str(v) for k, v in dict(data.get("last_tool") or {}).items()}
        self._totals = Counter(dict(data.get("totals") or {}))
        freq_path = Path(path).with_suffix(".frequency.json")
        if freq_path.exists():
            self._fallback.load(str(freq_path))
