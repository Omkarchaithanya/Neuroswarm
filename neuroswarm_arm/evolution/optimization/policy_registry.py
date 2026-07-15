"""Immutable policy registry with active + canary slots (blue/green style)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from neuroswarm_arm.evolution.models.policy import PolicyConstraints, RuntimePolicy


class PolicyRegistry:
    def __init__(self, store_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._policies: dict[str, RuntimePolicy] = {}
        self._active_id: str | None = None
        self._canary_id: str | None = None
        self._canary_percent: float = 0.0
        self._shadow_id: str | None = None
        self._store_path = store_path
        if store_path and store_path.exists():
            self._load(store_path)

    def register(self, policy: RuntimePolicy) -> RuntimePolicy:
        with self._lock:
            self._policies[policy.id] = policy
            self._persist()
            return policy

    def get(self, policy_id: str) -> RuntimePolicy | None:
        with self._lock:
            return self._policies.get(policy_id)

    def list_policies(self) -> list[RuntimePolicy]:
        with self._lock:
            return list(self._policies.values())

    def set_active(self, policy_id: str) -> RuntimePolicy:
        with self._lock:
            if policy_id not in self._policies:
                raise KeyError(f"unknown policy: {policy_id}")
            self._active_id = policy_id
            self._canary_id = None
            self._canary_percent = 0.0
            self._persist()
            return self._policies[policy_id]

    def set_canary(self, policy_id: str, *, percent: float = 10.0) -> RuntimePolicy:
        with self._lock:
            if policy_id not in self._policies:
                raise KeyError(f"unknown policy: {policy_id}")
            self._canary_id = policy_id
            self._canary_percent = float(percent)
            self._persist()
            return self._policies[policy_id]

    def set_shadow(self, policy_id: str) -> RuntimePolicy:
        with self._lock:
            if policy_id not in self._policies:
                raise KeyError(f"unknown policy: {policy_id}")
            self._shadow_id = policy_id
            self._persist()
            return self._policies[policy_id]

    def clear_canary(self) -> None:
        with self._lock:
            self._canary_id = None
            self._canary_percent = 0.0
            self._persist()

    def clear_shadow(self) -> None:
        with self._lock:
            self._shadow_id = None
            self._persist()

    def active(self) -> RuntimePolicy | None:
        with self._lock:
            return self._policies.get(self._active_id) if self._active_id else None

    def canary(self) -> RuntimePolicy | None:
        with self._lock:
            return self._policies.get(self._canary_id) if self._canary_id else None

    def shadow(self) -> RuntimePolicy | None:
        with self._lock:
            return self._policies.get(self._shadow_id) if self._shadow_id else None

    def canary_percent(self) -> float:
        with self._lock:
            return self._canary_percent

    def resolve(self, *, agent_id: str = "") -> RuntimePolicy | None:
        """Sticky percentage canary by agent_id hash."""
        with self._lock:
            active = self._policies.get(self._active_id) if self._active_id else None
            canary = self._policies.get(self._canary_id) if self._canary_id else None
            if canary is None or self._canary_percent <= 0:
                return active
            bucket = abs(hash(agent_id or "default")) % 100
            if bucket < self._canary_percent:
                return canary
            return active

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_id": self._active_id,
                "canary_id": self._canary_id,
                "canary_percent": self._canary_percent,
                "shadow_id": self._shadow_id,
                "n_policies": len(self._policies),
            }

    def _persist(self) -> None:
        if not self._store_path:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_id": self._active_id,
            "canary_id": self._canary_id,
            "canary_percent": self._canary_percent,
            "shadow_id": self._shadow_id,
            "policies": [p.to_dict() for p in self._policies.values()],
        }
        self._store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        from datetime import datetime

        for raw in data.get("policies", []):
            c = raw.get("constraints") or {}
            constraints = PolicyConstraints(
                max_latency_ms=float(c.get("max_latency_ms", 5000)),
                min_accept_rate=float(c.get("min_accept_rate", 0.5)),
                max_cost_usd=float(c.get("max_cost_usd", 0.05)),
                max_kv_pressure=float(c.get("max_kv_pressure", 0.9)),
                max_cpu_util=float(c.get("max_cpu_util", 0.95)),
                min_quality=float(c.get("min_quality", 0.0)),
                min_tool_success=float(c.get("min_tool_success", 0.0)),
                extras=dict(c.get("extras") or {}),
            )
            created = raw.get("created_at")
            try:
                created_at = datetime.fromisoformat(created) if created else datetime.utcnow()
            except Exception:
                created_at = datetime.utcnow()
            policy = RuntimePolicy(
                id=raw["id"],
                version=raw.get("version", "v0"),
                created_at=created_at,
                target_layers=frozenset(raw.get("target_layers") or []),
                parameters=dict(raw.get("parameters") or {}),
                expected_reward=float(raw.get("expected_reward", 0)),
                confidence=float(raw.get("confidence", 0.5)),
                constraints=constraints,
                rollback_policy_id=raw.get("rollback_policy_id"),
                parent_policy_id=raw.get("parent_policy_id"),
                content_hash=raw.get("content_hash", ""),
                explanation=raw.get("explanation", ""),
            )
            self._policies[policy.id] = policy
        self._active_id = data.get("active_id")
        self._canary_id = data.get("canary_id")
        self._canary_percent = float(data.get("canary_percent") or 0)
        self._shadow_id = data.get("shadow_id")
