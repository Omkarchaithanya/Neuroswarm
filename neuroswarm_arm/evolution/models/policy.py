"""Immutable versioned RuntimePolicy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class PolicyConstraints:
    max_latency_ms: float = 5000.0
    min_accept_rate: float = 0.5
    max_cost_usd: float = 0.05
    max_kv_pressure: float = 0.9
    max_cpu_util: float = 0.95
    min_quality: float = 0.0
    min_tool_success: float = 0.0
    extras: Mapping[str, float] = field(default_factory=dict)


def content_hash_for(parameters: Mapping[str, Any], target_layers: frozenset[str]) -> str:
    payload = {
        "parameters": dict(sorted(parameters.items(), key=lambda kv: kv[0])),
        "target_layers": sorted(target_layers),
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """Immutable runtime policy object. Optimization never edits live config in place."""

    id: str
    version: str
    created_at: datetime
    target_layers: frozenset[str]
    parameters: Mapping[str, Any]
    expected_reward: float
    confidence: float
    constraints: PolicyConstraints
    rollback_policy_id: str | None = None
    parent_policy_id: str | None = None
    content_hash: str = ""
    explanation: str = ""

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        version: str,
        parameters: Mapping[str, Any],
        target_layers: frozenset[str] | set[str] | list[str],
        expected_reward: float = 0.0,
        confidence: float = 0.5,
        constraints: PolicyConstraints | None = None,
        rollback_policy_id: str | None = None,
        parent_policy_id: str | None = None,
        explanation: str = "",
    ) -> RuntimePolicy:
        layers = frozenset(target_layers)
        params = dict(parameters)
        return cls(
            id=policy_id,
            version=version,
            created_at=_utcnow(),
            target_layers=layers,
            parameters=params,
            expected_reward=float(expected_reward),
            confidence=float(confidence),
            constraints=constraints or PolicyConstraints(),
            rollback_policy_id=rollback_policy_id,
            parent_policy_id=parent_policy_id,
            content_hash=content_hash_for(params, layers),
            explanation=explanation,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "target_layers": sorted(self.target_layers),
            "parameters": dict(self.parameters),
            "expected_reward": self.expected_reward,
            "confidence": self.confidence,
            "constraints": {
                "max_latency_ms": self.constraints.max_latency_ms,
                "min_accept_rate": self.constraints.min_accept_rate,
                "max_cost_usd": self.constraints.max_cost_usd,
                "max_kv_pressure": self.constraints.max_kv_pressure,
                "max_cpu_util": self.constraints.max_cpu_util,
                "min_quality": self.constraints.min_quality,
                "min_tool_success": self.constraints.min_tool_success,
                "extras": dict(self.constraints.extras),
            },
            "rollback_policy_id": self.rollback_policy_id,
            "parent_policy_id": self.parent_policy_id,
            "content_hash": self.content_hash,
            "explanation": self.explanation,
        }
