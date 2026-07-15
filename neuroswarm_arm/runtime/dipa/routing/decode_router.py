"""Decode-phase pool selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..interfaces.types import ExecutionPlan, InferenceRequest, PoolKind


@dataclass(slots=True)
class DecodeRoute:
    pool: PoolKind
    affinity_hint: dict[str, Any]


class DecodeRouter:
    """Pin decode work to :attr:`PoolKind.DECODE`."""

    def route(self, req: InferenceRequest, plan: ExecutionPlan) -> DecodeRoute:
        plan.decode_pool = PoolKind.DECODE
        hint: dict[str, Any] = {
            "phase": "decode",
            "pool": PoolKind.DECODE.value,
            "session_id": req.session_id,
            "stream": bool(req.stream or plan.stream),
            "max_tokens": req.max_tokens,
        }
        plan.metadata.setdefault("decode", {})
        plan.metadata["decode"]["affinity_hint"] = hint
        return DecodeRoute(pool=PoolKind.DECODE, affinity_hint=hint)

    def select_pool(self, req: InferenceRequest, plan: ExecutionPlan) -> PoolKind:
        return self.route(req, plan).pool
