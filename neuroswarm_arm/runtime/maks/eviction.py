"""Eviction engine — scored (default) / LRU/LFU/Clock/ARC/cost; pinned never evicted."""

from __future__ import annotations

from collections import deque
from typing import Any

from .exceptions import KVPinnedError
from .interfaces import IEvictionPolicy
from .models import EvictionPolicyName, KVRegistryRecord
from .policies import build_policy
from .policies.scored import ScoredEvictionPolicy
from .registry import KVRegistry


class EvictionEngine:
    def __init__(
        self,
        registry: KVRegistry,
        policy: IEvictionPolicy | None = None,
        *,
        policy_name: EvictionPolicyName = EvictionPolicyName.SCORED,
    ) -> None:
        self.registry = registry
        self.policy = policy or build_policy(policy_name)
        self.policy_name = policy_name
        self._clock: deque[str] = deque()
        self._clock_ref: dict[str, bool] = {}
        self.eviction_count = 0
        self._page_signals: dict[str, dict[str, Any]] = {}

    def set_page_signals(self, signals: dict[str, dict[str, Any]]) -> None:
        self._page_signals = signals
        if isinstance(self.policy, ScoredEvictionPolicy):
            self.policy.set_page_signals(signals)

    def set_pressure(self, pressure: float) -> None:
        if isinstance(self.policy, ScoredEvictionPolicy):
            self.policy.set_pressure(pressure)

    def observe_access(self, kv_id: str) -> None:
        self._clock_ref[kv_id] = True
        if kv_id not in self._clock:
            self._clock.append(kv_id)
        if hasattr(self.policy, "observe"):
            self.policy.observe(kv_id, frequent=True)  # type: ignore[attr-defined]

    async def select_victims(
        self,
        *,
        bytes_needed: int = 0,
        count: int = 1,
        ref_aware: bool = True,
    ) -> list[str]:
        records = await self.registry.all_records()
        if ref_aware:
            records = [r for r in records if r.refcount <= 1 and not r.pinned]
        else:
            records = [r for r in records if not r.pinned]

        if self.policy_name is EvictionPolicyName.CLOCK:
            return self._clock_select(records, count=max(count, 1 if bytes_needed <= 0 else count))

        if isinstance(self.policy, ScoredEvictionPolicy) and self._page_signals:
            self.policy.set_page_signals(self._page_signals)

        return self.policy.select_victims(records, bytes_needed=bytes_needed, count=count)

    def _clock_select(self, records: list[KVRegistryRecord], *, count: int) -> list[str]:
        by_id = {r.kv_id: r for r in records}
        for kid in by_id:
            if kid not in self._clock:
                self._clock.append(kid)
                self._clock_ref.setdefault(kid, False)
        victims: list[str] = []
        scanned = 0
        limit = max(len(self._clock) * 2, count)
        while len(victims) < count and self._clock and scanned < limit:
            scanned += 1
            kid = self._clock.popleft()
            if kid not in by_id:
                self._clock_ref.pop(kid, None)
                continue
            if self._clock_ref.get(kid, False):
                self._clock_ref[kid] = False
                self._clock.append(kid)
                continue
            victims.append(kid)
            self._clock_ref.pop(kid, None)
        return victims

    async def ensure_not_pinned(self, kv_id: str) -> None:
        rec = await self.registry.get(kv_id)
        if rec is not None and rec.pinned:
            raise KVPinnedError(kv_id)
