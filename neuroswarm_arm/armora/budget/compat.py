"""Compat adapter — ArmoraBudgetPolicy over unified Budget Envelope ledger."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from .config import BudgetRuntimeConfig, load_budget_config
from .service import BudgetService, build_budget_service


@dataclass
class BudgetConfig:
    """Legacy ARMORA budget config — maps onto BudgetRuntimeConfig defaults."""

    max_cost_usd: float = 0.05
    max_memory_bytes: int = 8 * 1024 * 1024 * 1024
    max_cache_entries: int = 10_000
    max_ttl_s: float = 3600.0
    policies: list[str] = field(default_factory=lambda: ["cost", "memory"])

    def to_runtime_overrides(self) -> dict[str, Any]:
        return {
            "cost_usd": self.max_cost_usd,
            "memory_bytes": self.max_memory_bytes,
        }


class ArmoraBudgetPolicy:
    """Implements MAKS IARMORAPolicy-compatible surface via BudgetService ledger."""

    def __init__(
        self,
        config: BudgetConfig | BudgetRuntimeConfig | None = None,
        *,
        service: BudgetService | None = None,
        memory: Any | None = None,
    ) -> None:
        self._legacy = config if isinstance(config, BudgetConfig) else BudgetConfig()
        if isinstance(config, BudgetRuntimeConfig):
            runtime_cfg = config
        else:
            runtime_cfg = load_budget_config()
            runtime_cfg.default_cost_usd = float(self._legacy.max_cost_usd)
            runtime_cfg.default_memory_bytes = int(self._legacy.max_memory_bytes)
        self.config = self._legacy
        self.service = service or build_budget_service(runtime_cfg)
        self.memory = memory
        self._lock = threading.Lock()
        self._spent_usd = 0.0
        self._memory_bytes = 0
        self._entries = 0
        self._session_envelope_id: str | None = None
        self.max_cost_usd = float(self._legacy.max_cost_usd)
        self.policies = list(self._legacy.policies)

    def _ensure_session(self) -> str:
        if self._session_envelope_id:
            return self._session_envelope_id
        eid = self._sync_create_envelope()
        self._session_envelope_id = eid
        return eid

    def _sync_create_envelope(self) -> str:
        """Create frozen envelope without requiring an event loop (thread helper)."""
        from .envelope import build_envelope_from_template
        from .policy import PolicyEngine
        from .plugins import BudgetPluginRegistry

        registry = self.service.registry
        compiler = registry.policy_compiler()
        policy = PolicyEngine(compiler)
        template = policy.compile(
            agent_role="default",
            overrides=self._legacy.to_runtime_overrides(),
        )
        envelope = build_envelope_from_template(
            template,
            self.service.config,
            request_id=f"armora-session-{uuid4().hex[:12]}",
            tenant_id="default",
        )
        frozen = envelope.freeze()
        self.service.tracker.register(frozen)
        return str(frozen.envelope_id)

    def snapshot(self) -> Any:
        from neuroswarm_arm.runtime.maks.models import (
            ARMORAPolicySnapshot,
            EvictionPolicyName,
        )

        return ARMORAPolicySnapshot(
            max_memory_bytes=self.config.max_memory_bytes,
            max_cost=self.config.max_cost_usd,
            max_cache_entries=self.config.max_cache_entries,
            eviction_policy=EvictionPolicyName.LRU,
            ttl_s=float(self.config.max_ttl_s),
            budget=self.config.max_cost_usd,
            priority=0,
        )

    def admit(self, size_bytes: int, priority: int = 0) -> bool:
        with self._lock:
            if self._memory_bytes + size_bytes > self.config.max_memory_bytes:
                if priority < 10:
                    return False
            if self._entries + 1 > self.config.max_cache_entries and priority < 5:
                return False
            eid = self._ensure_session()
            ok = self.service.tracker.reserve(
                eid, {"memory_bytes": float(max(0, size_bytes)), "kv_bytes": float(max(0, size_bytes))}
            )
            if not ok and priority < 10:
                return False
            if ok:
                self.service.tracker.reconcile(
                    eid,
                    {
                        "memory_bytes": float(max(0, size_bytes)),
                        "kv_bytes": float(max(0, size_bytes)),
                    },
                    reserved={
                        "memory_bytes": float(max(0, size_bytes)),
                        "kv_bytes": float(max(0, size_bytes)),
                    },
                )
            self._memory_bytes += max(0, size_bytes)
            self._entries += 1
            return True

    def charge(self, cost_usd: float) -> bool:
        with self._lock:
            if self._spent_usd + cost_usd > self.config.max_cost_usd:
                return False
            eid = self._ensure_session()
            ok = self.service.tracker.consume(eid, {"cost_usd": float(cost_usd)})
            if not ok:
                return False
            self._spent_usd += cost_usd
            mem = self.memory
            if mem is not None:
                try:
                    from neuroswarm_arm.runtime.memory.sinks import remember_armora_cost

                    remember_armora_cost(mem, owner="default", cost_usd=float(cost_usd))
                except Exception:
                    pass
            return True

    def release(self, size_bytes: int = 0) -> None:
        with self._lock:
            self._memory_bytes = max(0, self._memory_bytes - max(0, size_bytes))
            self._entries = max(0, self._entries - 1)

    def status(self) -> Mapping[str, Any]:
        with self._lock:
            remaining = None
            if self._session_envelope_id:
                try:
                    remaining = self.service.tracker.cost_remaining(self._session_envelope_id)
                except KeyError:
                    remaining = None
            return {
                "spent_usd": self._spent_usd,
                "max_cost_usd": self.config.max_cost_usd,
                "memory_bytes": self._memory_bytes,
                "max_memory_bytes": self.config.max_memory_bytes,
                "entries": self._entries,
                "max_cache_entries": self.config.max_cache_entries,
                "envelope_id": self._session_envelope_id,
                "remaining_usd": remaining,
            }

    def bind_request_envelope(self, envelope_id: str) -> None:
        """Point subsequent admit/charge at a per-request frozen envelope."""
        with self._lock:
            self._session_envelope_id = envelope_id
