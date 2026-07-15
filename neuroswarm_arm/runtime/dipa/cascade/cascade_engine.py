"""Cascade engine — multi-tier generate with confidence escalation."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ..interfaces.cascade import ICascadeEngine
from ..interfaces.types import ExecutionPlan, GenerateResult, InferenceRequest
from .cascade_executor import CascadeExecutor, SupportsBackendLookup, approx_tokens
from .cascade_policy import CascadePolicy, TierPolicy
from .cascade_validator import CascadeValidator
from .self_speculation import SelfSpeculationEngine
from .verifier import Verifier

if TYPE_CHECKING:
    from ..execution.execution_context import ExecutionContext

MetricsCallback = Callable[[str, Mapping[str, float]], None]


class CascadeEngine(ICascadeEngine):
    """Try policy tiers in order; escalate when confidence is below threshold.

    Dependencies
    ------------
    policy:
        Tier ladder and confidence knobs (from ``cascade.yaml``).
    registry:
        Backend lookup by tier backend name (``tier1`` / ``tier2`` / ``tier3``).
    verifier:
        Confidence scorer; defaults from ``policy.confidence``.
    metrics:
        Optional ``(event, fields)`` callback for tier / confidence telemetry.
    """

    def __init__(
        self,
        policy: CascadePolicy,
        registry: SupportsBackendLookup,
        verifier: Verifier | None = None,
        *,
        validator: CascadeValidator | None = None,
        speculation: SelfSpeculationEngine | None = None,
        metrics: MetricsCallback | None = None,
        executor: CascadeExecutor | None = None,
    ) -> None:
        self.policy = policy
        self.registry = registry
        self.verifier = verifier or Verifier(policy.confidence)
        self.validator = validator or CascadeValidator(self.verifier)
        self.speculation = speculation or SelfSpeculationEngine.from_policy(
            policy.speculation
        )
        self.metrics = metrics
        self.executor = executor or CascadeExecutor(registry)

    async def run(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        ctx: ExecutionContext,
    ) -> GenerateResult:
        start_tier = max(1, int(plan.cascade_start_tier or 1))
        tiers = self.policy.tiers_from(start_tier)
        if not tiers:
            raise RuntimeError("cascade policy has no tiers to execute")

        t0 = time.monotonic()
        last: GenerateResult | None = None
        prompt_tokens = approx_tokens(req.prompt_text)

        speculative = bool(plan.self_speculation and self.speculation.enabled)
        draft = self.speculation.draft_suffix(req.prompt_text) if speculative else None
        if draft:
            self._emit("cascade_draft", {"draft_tokens": float(approx_tokens(draft))})

        for index, tier in enumerate(tiers):
            result = await self.executor.generate_tier(
                req,
                tier,
                ctx,
                quant=plan.quant,
                speculative=speculative,
                kv_handle=ctx.kv_handle,
                max_tokens=req.max_tokens,
            )
            last = result
            conf = self.verifier.score(result.text)
            self._emit(
                "cascade_tier",
                {
                    "tier": float(tier.id),
                    "confidence": conf,
                    "threshold": float(tier.acceptance_threshold),
                    "latency_ms": float(result.latency_ms),
                },
            )

            accepted = self.validator.accepts(result.text, tier.acceptance_threshold)
            # Final tier always accepted (threshold may be 0.0).
            is_last = index == len(tiers) - 1
            if accepted or is_last:
                return self._finalize(
                    result,
                    tier=tier,
                    confidence=conf,
                    prompt_tokens=prompt_tokens,
                    t0=t0,
                    escalated=index > 0,
                )

            self._emit(
                "cascade_escalate",
                {"from_tier": float(tier.id), "confidence": conf},
            )

        assert last is not None  # tiers non-empty
        return self._finalize(
            last,
            tier=tiers[-1],
            confidence=self.verifier.score(last.text),
            prompt_tokens=prompt_tokens,
            t0=t0,
            escalated=True,
        )

    def _finalize(
        self,
        result: GenerateResult,
        *,
        tier: TierPolicy,
        confidence: float,
        prompt_tokens: int,
        t0: float,
        escalated: bool,
    ) -> GenerateResult:
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        metrics: dict[str, float] = dict(result.metrics)
        metrics.update(
            {
                "confidence": confidence,
                "escalated": 1.0 if escalated else 0.0,
                "cascade_latency_ms": elapsed_ms,
            }
        )
        self._emit(
            "cascade_complete",
            {
                "tier_used": float(tier.id),
                "confidence": confidence,
                "latency_ms": elapsed_ms,
            },
        )
        return GenerateResult(
            text=result.text,
            prompt_tokens=result.prompt_tokens or prompt_tokens,
            completion_tokens=result.completion_tokens or approx_tokens(result.text),
            latency_ms=elapsed_ms,
            ttft_ms=result.ttft_ms,
            backend=result.backend or tier.backend,
            model=result.model or tier.model,
            quant=result.quant,
            tier_used=tier.id,
            raw={**result.raw, "confidence": confidence},
            metrics=metrics,
        )

    def _emit(self, event: str, fields: Mapping[str, float]) -> None:
        if self.metrics is not None:
            self.metrics(event, fields)
