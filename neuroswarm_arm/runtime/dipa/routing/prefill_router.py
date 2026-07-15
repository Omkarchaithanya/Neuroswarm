"""Prefill-phase pool and affinity hint selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..interfaces.types import ExecutionPlan, InferenceRequest, PoolKind


@dataclass(slots=True)
class PrefillRoute:
    pool: PoolKind
    affinity_hint: dict[str, Any]


class PrefillRouter:
    """Pin prefill work to :attr:`PoolKind.PREFILL` with an affinity hint."""

    def route(self, req: InferenceRequest, plan: ExecutionPlan) -> PrefillRoute:
        plan.prefill_pool = PoolKind.PREFILL
        hint: dict[str, Any] = {
            "phase": "prefill",
            "pool": PoolKind.PREFILL.value,
            "session_id": req.session_id,
            "prefer_locality": True,
            "prompt_tokens_est": req.prompt_length,
        }
        plan.metadata.setdefault("prefill", {})
        plan.metadata["prefill"]["affinity_hint"] = hint
        return PrefillRoute(pool=PoolKind.PREFILL, affinity_hint=hint)

    def select_pool(self, req: InferenceRequest, plan: ExecutionPlan) -> PoolKind:
        return self.route(req, plan).pool
