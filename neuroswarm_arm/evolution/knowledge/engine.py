"""In-memory + Mem0 + OKF knowledge stores."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Mapping

from neuroswarm_arm.evolution.interfaces.knowledge import KnowledgeStore, KnowledgeView
from neuroswarm_arm.evolution.models.observation import Episode, NormalizedObservation, Outcome
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


class InMemoryKnowledgeStore(KnowledgeStore):
    def __init__(self, *, max_obs: int = 500, max_episodes: int = 200) -> None:
        self._lock = threading.RLock()
        self._obs: list[NormalizedObservation] = []
        self._episodes: list[Episode] = []
        self._policies: dict[str, RuntimePolicy] = {}
        self._reflections: list[str] = []
        self._max_obs = max_obs
        self._max_episodes = max_episodes
        self._active: RuntimePolicy | None = None

    def store_observation(self, obs: NormalizedObservation) -> None:
        with self._lock:
            self._obs.append(obs)
            if len(self._obs) > self._max_obs:
                self._obs = self._obs[-self._max_obs :]

    def store_episode(self, episode: Episode) -> None:
        with self._lock:
            self._episodes.append(episode)
            if len(self._episodes) > self._max_episodes:
                self._episodes = self._episodes[-self._max_episodes :]

    def store_outcome(self, episode_id: str, outcome: Outcome) -> None:
        with self._lock:
            for i, ep in enumerate(self._episodes):
                if ep.episode_id == episode_id:
                    self._episodes[i] = Episode(
                        episode_id=ep.episode_id,
                        started_at=ep.started_at,
                        ended_at=ep.ended_at,
                        policy_id=ep.policy_id,
                        policy_version=ep.policy_version,
                        observations=ep.observations,
                        outcome=outcome,
                        metadata=ep.metadata,
                    )
                    return

    def store_policy(self, policy: RuntimePolicy) -> None:
        with self._lock:
            self._policies[policy.id] = policy
            self._active = policy

    def store_reflection(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        with self._lock:
            self._reflections.append(text)
            if len(self._reflections) > 200:
                self._reflections = self._reflections[-200:]

    def set_active(self, policy: RuntimePolicy | None) -> None:
        with self._lock:
            self._active = policy

    def view(self, *, limit: int = 50) -> KnowledgeView:
        with self._lock:
            obs = tuple(self._obs[-limit:])
            eps = tuple(self._episodes[-limit:])
            means: dict[str, float] = {}
            counts: dict[str, int] = {}
            for o in obs:
                for k, v in o.metrics.items():
                    means[k] = means.get(k, 0.0) + float(v)
                    counts[k] = counts.get(k, 0) + 1
            for k in list(means):
                means[k] = means[k] / max(counts[k], 1)
            return KnowledgeView(
                recent_observations=obs,
                recent_episodes=eps,
                active_policy=self._active,
                aggregate_metrics=means,
                reflections=tuple(self._reflections[-20:]),
            )


class Mem0KnowledgeStore(KnowledgeStore):
    """Writes evolution memory via NeuroMemory when available; always keeps local mirror."""

    def __init__(self, memory: Any | None = None, *, fallback: InMemoryKnowledgeStore | None = None) -> None:
        self.memory = memory
        self.fallback = fallback or InMemoryKnowledgeStore()

    def store_observation(self, obs: NormalizedObservation) -> None:
        self.fallback.store_observation(obs)
        self._remember(
            f"obs:{obs.source}:{json.dumps(dict(obs.metrics), sort_keys=True)[:500]}",
            kind="observation",
        )

    def store_episode(self, episode: Episode) -> None:
        self.fallback.store_episode(episode)
        self._remember(f"episode:{episode.episode_id}", kind="episode")

    def store_outcome(self, episode_id: str, outcome: Outcome) -> None:
        self.fallback.store_outcome(episode_id, outcome)
        self._remember(
            f"outcome:{episode_id}:scalar={outcome.reward.scalar:.4f}",
            kind="outcome",
        )

    def store_policy(self, policy: RuntimePolicy) -> None:
        self.fallback.store_policy(policy)
        self._remember(
            f"policy:{policy.id}:{policy.version}:{policy.content_hash}",
            kind="policy",
            metadata={"policy_id": policy.id, "version": policy.version},
        )

    def store_reflection(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        self.fallback.store_reflection(text, metadata=metadata)
        neuro = self._neuro()
        if neuro is not None and hasattr(neuro, "remember_reflection"):
            try:
                neuro.remember_reflection(text, owner="arop", **(metadata or {}))
                return
            except Exception:
                pass
        self._remember(text, kind="reflection", metadata=metadata)

    def view(self, *, limit: int = 50) -> KnowledgeView:
        return self.fallback.view(limit=limit)

    def set_active(self, policy: RuntimePolicy | None) -> None:
        self.fallback.set_active(policy)

    def _neuro(self) -> Any | None:
        if self.memory is None:
            return None
        return getattr(self.memory, "neuro", self.memory)

    def _remember(self, content: str, *, kind: str, metadata: Mapping[str, Any] | None = None) -> None:
        neuro = self._neuro()
        if neuro is None:
            return
        try:
            if hasattr(neuro, "remember_evolution"):
                neuro.remember_evolution(content, owner="arop", tags=["arop", kind], **(metadata or {}))
        except Exception:
            return


class OKFKnowledgeStore:
    """Engineering memory — policy history into OKF sources via evolution_sink."""

    def __init__(self, source_root: Path) -> None:
        self.source_root = Path(source_root)

    def write_policy(self, policy: RuntimePolicy) -> Path:
        from neuroswarm_arm.runtime.okf.connectors.evolution_sink import write_evolved_prompt

        body = (
            f"# AROP Policy `{policy.id}`\n\n"
            f"- version: `{policy.version}`\n"
            f"- hash: `{policy.content_hash}`\n"
            f"- layers: {', '.join(sorted(policy.target_layers))}\n"
            f"- expected_reward: {policy.expected_reward}\n"
            f"- confidence: {policy.confidence}\n\n"
            f"## Parameters\n\n```json\n{json.dumps(dict(policy.parameters), indent=2)}\n```\n\n"
            f"## Explanation\n\n{policy.explanation or '_none_'}\n"
        )
        rel = f"domains/architecture/policies/{policy.id}-{policy.version}.md"
        return write_evolved_prompt(
            self.source_root,
            rel,
            body,
            frontmatter={
                "type": "policy",
                "title": f"AROP {policy.id}",
                "okf_version": "1.0",
                "arop_policy_id": policy.id,
                "arop_version": policy.version,
                "content_hash": policy.content_hash,
            },
        )


class KnowledgeEngine:
    """Normalize → Event → Episode → Policy → Outcome pipeline glue."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        okf: OKFKnowledgeStore | None = None,
    ) -> None:
        self.store = store
        self.okf = okf

    def ingest(self, observations: list[NormalizedObservation]) -> None:
        self.store.store_observations(observations)

    def record_episode(self, episode: Episode) -> None:
        self.store.store_episode(episode)

    def record_policy(self, policy: RuntimePolicy) -> Path | None:
        self.store.store_policy(policy)
        if self.okf is not None:
            try:
                return self.okf.write_policy(policy)
            except Exception:
                return None
        return None

    def view(self, *, limit: int = 50) -> KnowledgeView:
        return self.store.view(limit=limit)
