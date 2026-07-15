"""AWPP encoded state vector for prediction and RL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(slots=True)
class AWPPState:
    """Normalized state snapshot consumed by predictors and policies."""

    agent_id: str = ""
    session_id: str = ""
    workflow_id: str = ""
    current_node: str = ""
    feature_vector: list[float] = field(default_factory=list)
    transition_probs: dict[str, float] = field(default_factory=dict)
    hardware: dict[str, float] = field(default_factory=dict)
    cache_pressure: float = 0.0
    kv_pressure: float = 0.0
    latency_slo_ms: float = 150.0
    horizon_s: float = 5.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "current_node": self.current_node,
            "feature_vector": list(self.feature_vector),
            "transition_probs": dict(self.transition_probs),
            "hardware": dict(self.hardware),
            "cache_pressure": self.cache_pressure,
            "kv_pressure": self.kv_pressure,
            "latency_slo_ms": self.latency_slo_ms,
            "horizon_s": self.horizon_s,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AWPPState:
        return cls(
            agent_id=str(data.get("agent_id") or ""),
            session_id=str(data.get("session_id") or ""),
            workflow_id=str(data.get("workflow_id") or ""),
            current_node=str(data.get("current_node") or ""),
            feature_vector=[float(x) for x in (data.get("feature_vector") or [])],
            transition_probs={
                str(k): float(v) for k, v in dict(data.get("transition_probs") or {}).items()
            },
            hardware={str(k): float(v) for k, v in dict(data.get("hardware") or {}).items()},
            cache_pressure=float(data.get("cache_pressure") or 0.0),
            kv_pressure=float(data.get("kv_pressure") or 0.0),
            latency_slo_ms=float(data.get("latency_slo_ms") or 150.0),
            horizon_s=float(data.get("horizon_s") or 5.0),
            metadata=dict(data.get("metadata") or {}),
        )
