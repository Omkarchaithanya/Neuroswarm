"""Cascade policy engine — fuses classifier + peer telemetry into a decision."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from neuroswarm_arm.runtime.armcascade.config.loader import default_thresholds
from neuroswarm_arm.runtime.armcascade.interfaces.proposal import CascadePolicyEngine
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    Classification,
    PolicyDecision,
    TaskKind,
    ThresholdSet,
)
from neuroswarm_arm.runtime.armcascade.policies.cost_model import (
    CostSignals,
    cost_model_enabled,
    should_skip_spec,
)

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan


class DefaultCascadePolicyEngine(CascadePolicyEngine):
    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self.base = default_thresholds(self.config)
        self._last_skip_reason: str = ""

    def apply(self, plan: ExecutionPlan, signals: CostSignals) -> ExecutionPlan:
        """Mutate plan to skip speculation when cost model says so (G15)."""
        self._last_skip_reason = ""
        if not cost_model_enabled(self.config):
            return plan
        skip, reason = should_skip_spec(plan, signals)
        if not skip:
            return plan
        self._last_skip_reason = reason
        plan.speculation = False
        if getattr(plan, "self_speculation", False):
            plan.self_speculation = False
        meta = dict(getattr(plan, "metadata", None) or {})
        meta["ascr_skip_spec_reason"] = reason
        meta["ascr_skip_spec"] = True
        plan.metadata = meta
        return plan

    def decide(
        self,
        classification: Classification,
        plan: ExecutionPlan | None = None,
        telemetry: dict | None = None,
    ) -> PolicyDecision:
        tel = dict(telemetry or {})
        defaults = dict(self.config.get("defaults") or {})

        proposal = classification.recommended_strategy or str(
            defaults.get("proposal_strategy", "draft_model")
        )
        verify = classification.recommended_verify or str(
            defaults.get("verify_strategy", "block")
        )
        graph = classification.recommended_graph or str(
            self.config.get("default_graph", "default_linear")
        )

        # Plan metadata overrides (SpeculationRouter / DecisionEngine / AQR cascade_profiles).
        meta = dict(getattr(plan, "metadata", None) or {})
        spec = dict(meta.get("speculation") or {})
        if spec.get("strategy"):
            proposal = str(spec["strategy"])
        if spec.get("verify_strategy"):
            verify = str(spec["verify_strategy"])
        if spec.get("graph"):
            graph = str(spec["graph"])

        # Wire cascade_profiles.yaml floors into thresholds / quant metadata.
        aqr_floor = meta.get("aqr_quality_floor")
        if aqr_floor is None:
            try:
                from neuroswarm_arm.runtime.aqr import cascade_profile_for_tier

                tier_hint = int(meta.get("aqr_cascade_tier") or meta.get("tier") or 1)
                profile = cascade_profile_for_tier(tier_hint)
                if profile.get("quality_floor") is not None:
                    aqr_floor = float(profile["quality_floor"])
                    meta = {
                        **meta,
                        "aqr_quality_floor": aqr_floor,
                        "aqr_preferred_quants": list(profile.get("preferred_quants") or []),
                        "aqr_max_bits": float(profile.get("max_bits", 0) or 0),
                    }
            except Exception:
                aqr_floor = None

        thresholds = ThresholdSet(
            draft_len=int(spec.get("draft_len", self.base.draft_len)),
            accept_threshold=float(
                spec.get(
                    "accept_threshold",
                    aqr_floor if aqr_floor is not None else self.base.accept_threshold,
                )
            ),
            verify_batch_size=int(
                spec.get("verify_batch_size", self.base.verify_batch_size)
            ),
            escalate_threshold=float(
                spec.get("escalate_threshold", self.base.escalate_threshold)
            ),
            speculation_depth=int(
                spec.get("speculation_depth", self.base.speculation_depth)
            ),
            max_rounds=int(spec.get("max_rounds", self.base.max_rounds)),
            quality_accept_threshold=float(
                spec.get(
                    "quality_accept_threshold",
                    getattr(self.base, "quality_accept_threshold", 0.55),
                )
            ),
            quality_early_accept_floor=float(
                spec.get(
                    "quality_early_accept_floor",
                    getattr(self.base, "quality_early_accept_floor", 0.52),
                )
            ),
        )

        # Peer-layer soft hints (connectors never owned here).
        if float(tel.get("kv_pressure", 0.0)) > 0.85:
            thresholds.draft_len = max(2, thresholds.draft_len // 2)
        if float(tel.get("aqr_prefer_fast", 0.0)) > 0.5:
            proposal = "self_speculation"
        if classification.task_kind == TaskKind.REASONING:
            thresholds.accept_threshold = min(0.95, thresholds.accept_threshold + 0.05)

        tiers = list(self.config.get("tiers") or [])
        draft_backend = "tier1"
        verify_backend = "tier2"
        escalate_backend = "tier3"
        for t in tiers:
            if not isinstance(t, Mapping):
                continue
            role = str(t.get("role", ""))
            backend = str(t.get("backend", ""))
            if role == "draft" and backend:
                draft_backend = backend
            elif role == "verify" and backend:
                verify_backend = backend
            elif role == "escalate" and backend:
                escalate_backend = backend

        return PolicyDecision(
            proposal_strategy=proposal,
            verify_strategy=verify,
            graph_name=graph,
            draft_backend=draft_backend,
            verify_backend=verify_backend,
            escalate_backend=escalate_backend,
            thresholds=thresholds,
            quality_cascade_fallback=bool(
                self.config.get("quality_cascade_fallback", True)
            ),
            metadata={
                "task_kind": classification.task_kind.value,
                "complexity": classification.complexity,
                "aqr_quality_floor": meta.get("aqr_quality_floor"),
                "aqr_preferred_quants": meta.get("aqr_preferred_quants"),
                "aqr_max_bits": meta.get("aqr_max_bits"),
            },
        )
