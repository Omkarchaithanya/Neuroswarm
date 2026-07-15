"""Speculation / self-speculation flags from cascade + ASCR config."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces.types import ExecutionPlan


class SpeculationRouter:
    """Apply cascade ``speculation`` block onto an :class:`ExecutionPlan`."""

    def __init__(self, cascade_cfg: Mapping[str, Any] | None = None) -> None:
        cfg = dict(cascade_cfg or {})
        spec = dict(cfg.get("speculation") or {})
        self.enabled = bool(spec.get("enabled", False))
        self.self_speculation = bool(spec.get("self_speculation", False))
        self.ngram_size = int(spec.get("ngram_size", 24))
        self.draft_min = int(spec.get("draft_min", 12))
        self.draft_max = int(spec.get("draft_max", 48))
        # ASCR extensions (optional keys in cascade.yaml or ascr merge).
        ascr = dict(cfg.get("ascr") or {})
        self.strategy = str(ascr.get("strategy") or spec.get("strategy") or "")
        self.verify_strategy = str(
            ascr.get("verify_strategy") or spec.get("verify_strategy") or "block"
        )
        self.graph = str(ascr.get("graph") or spec.get("graph") or "default_linear")
        self.draft_len = int(
            ascr.get("draft_len") or spec.get("draft_len") or self.draft_max or 8
        )
        self.accept_threshold = float(
            ascr.get("accept_threshold") or spec.get("accept_threshold") or 0.7
        )
        self.verify_batch_size = int(
            ascr.get("verify_batch_size") or spec.get("verify_batch_size") or 1
        )
        self.speculation_depth = int(
            ascr.get("speculation_depth") or spec.get("speculation_depth") or 1
        )

    def apply(self, plan: ExecutionPlan) -> ExecutionPlan:
        plan.speculation = self.enabled and plan.use_cascade
        plan.self_speculation = self.self_speculation and self.enabled
        plan.metadata.setdefault("speculation", {})
        strategy = self.strategy
        if not strategy:
            if plan.self_speculation:
                strategy = "self_speculation"
            elif plan.speculation:
                strategy = "draft_model"
            else:
                strategy = "draft_model"
        plan.metadata["speculation"].update(
            {
                "enabled": plan.speculation,
                "self_speculation": plan.self_speculation,
                "ngram_size": self.ngram_size,
                "draft_min": self.draft_min,
                "draft_max": self.draft_max,
                "strategy": strategy,
                "verify_strategy": self.verify_strategy,
                "graph": self.graph,
                "draft_len": self.draft_len,
                "accept_threshold": self.accept_threshold,
                "verify_batch_size": self.verify_batch_size,
                "speculation_depth": self.speculation_depth,
            }
        )
        return plan
