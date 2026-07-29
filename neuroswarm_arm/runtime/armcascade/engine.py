"""ASCREngine — Adaptive Speculative Cascade Runtime (ICascadeEngine)."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from neuroswarm_arm.runtime.armcascade.acceptance.engine import AdaptiveAcceptanceEngine
from neuroswarm_arm.runtime.armcascade.arm.adapters import ArmRuntimeAdapter, PerformixHook
from neuroswarm_arm.runtime.armcascade.classifier.heuristic import HeuristicRequestClassifier
from neuroswarm_arm.runtime.armcascade.confidence.engine import FusedConfidenceEngine
from neuroswarm_arm.runtime.armcascade.escalation.engine import GraphEscalationEngine
from neuroswarm_arm.runtime.armcascade.interfaces.proposal import (
    AcceptanceEngine,
    CascadePolicyEngine,
    ConfidenceEngine,
    EscalationEngine,
    ProposalStrategy,
    RequestClassifier,
    ThresholdEngine,
    VerifierStrategy,
)
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    ASCRRuntimeState,
    AcceptanceAction,
    AcceptanceSignals,
    EscalationState,
    PolicyDecision,
    Proposal,
    ProposalRequest,
    ThresholdInputs,
    VerifyMode,
    VerifyRequest,
    approx_tokens,
    build_messages,
)
from neuroswarm_arm.runtime.armcascade.metrics.prometheus import ASCRMetrics
from neuroswarm_arm.runtime.armcascade.policies.engine import DefaultCascadePolicyEngine
from neuroswarm_arm.runtime.armcascade.proposal.registry import (
    ProposalRegistry,
    VerifierRegistry,
)
from neuroswarm_arm.runtime.armcascade.thresholds.engine import AdaptiveThresholdEngine
from neuroswarm_arm.runtime.dipa.interfaces.cascade import ICascadeEngine
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    ExecutionPlan,
    GenerateRequest,
    GenerateResult,
    InferenceRequest,
)

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext

MetricsCallback = Callable[[str, Mapping[str, float]], None]


class ASCREngine(ICascadeEngine):
    """Propose → verify → accept → escalate → adapt loop."""

    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        registry: Any,
        graphs: Mapping[str, Any],
        classifier: RequestClassifier | None = None,
        policy_engine: CascadePolicyEngine | None = None,
        confidence: ConfidenceEngine | None = None,
        acceptance: AcceptanceEngine | None = None,
        thresholds: ThresholdEngine | None = None,
        escalation: EscalationEngine | None = None,
        proposers: ProposalRegistry | None = None,
        verifiers: VerifierRegistry | None = None,
        metrics: ASCRMetrics | None = None,
        arm: ArmRuntimeAdapter | None = None,
        performix: PerformixHook | None = None,
        legacy_metrics: MetricsCallback | None = None,
        memory_connector: Any | None = None,
    ) -> None:
        self.config = dict(config)
        self.registry = registry
        self.graphs = dict(graphs)
        self.classifier = classifier or HeuristicRequestClassifier()
        self.policy_engine = policy_engine or DefaultCascadePolicyEngine(self.config)
        self.confidence = confidence or FusedConfidenceEngine(
            dict((self.config.get("confidence") or {}).get("weights") or {})
        )
        self.acceptance = acceptance or AdaptiveAcceptanceEngine(self.confidence)
        self.thresholds = thresholds or AdaptiveThresholdEngine()
        self.escalation = escalation or GraphEscalationEngine()
        self.proposers = proposers or ProposalRegistry()
        self.verifiers = verifiers or VerifierRegistry()
        self.metrics = metrics or ASCRMetrics(
            alias_dipa=bool(
                (self.config.get("telemetry") or {}).get("alias_dipa_cascade", True)
            )
        )
        self.arm = arm or ArmRuntimeAdapter(self.config)
        self.performix = performix or PerformixHook()
        self.legacy_metrics = legacy_metrics
        # Optional ACR peer — connectors not ownership
        self.memory_connector = memory_connector
        self._history_accept = 0.7

    async def run(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        ctx: ExecutionContext,
    ) -> GenerateResult:
        t0 = time.monotonic()
        placement = self.arm.detect()
        self.arm.pin_current_thread("draft")

        classification = self.classifier.classify(req, plan)
        telemetry = {
            "kv_pressure": float(getattr(ctx, "kv_pressure", 0.0) or 0.0),
            "cpu_utilization": float(getattr(ctx, "cpu_utilization", 0.5) or 0.5),
            "cache_hit_ratio": float(getattr(ctx, "cache_hit_ratio", 0.0) or 0.0),
            "aqr_prefer_fast": float((plan.metadata or {}).get("aqr_prefer_fast", 0.0)),
        }
        policy = self.policy_engine.decide(classification, plan, telemetry)

        thr_in = ThresholdInputs(
            latency_budget_ms=float(req.latency_sla_ms or 4000.0),
            latency_used_ms=0.0,
            cpu_utilization=telemetry["cpu_utilization"],
            numa_locality=placement.locality,
            kv_pressure=telemetry["kv_pressure"],
            governor_cap=float(req.tool_confidence or 0.5),
            historical_acceptance=self._history_accept,
            complexity=classification.complexity,
            entropy_estimate=classification.entropy_estimate,
            base_draft_len=policy.thresholds.draft_len,
            base_accept_threshold=policy.thresholds.accept_threshold,
            base_escalate_threshold=policy.thresholds.escalate_threshold,
            base_verify_batch=policy.thresholds.verify_batch_size,
            base_depth=policy.thresholds.speculation_depth,
            base_max_rounds=int(policy.thresholds.max_rounds or 4),
        )
        thresholds = self.thresholds.compute(thr_in)
        policy.thresholds = thresholds

        state = ASCRRuntimeState(historical_acceptance=self._history_accept)
        graph = self.graphs.get(policy.graph_name) or self.graphs.get("default_linear")
        if graph is None:
            raise RuntimeError("no escalation graph configured")

        esc_state = EscalationState(
            current=graph.start,
            tool_needed=bool(req.tool_names or req.tool_schemas),
            memory_needed=classification.task_kind.value in {"rag", "multi_agent"},
        )

        proposer = self._get_proposer(policy)
        verifier = self._get_verifier(policy)
        await self._bind_strategies(proposer, verifier, ctx)

        # Quality-cascade path when plan disables speculation or strategy unavailable.
        use_quality = False
        if not plan.speculation and not plan.self_speculation:
            if policy.proposal_strategy not in {"self_speculation", "ngram", "suffix"}:
                use_quality = policy.quality_cascade_fallback

        committed = ""
        last_verify_text = ""
        last_backend = policy.draft_backend
        last_model = policy.draft_backend
        tier_used = 1
        last_logits = True
        last_agreement: float | None = None
        saw_logits = False

        while state.rounds < thresholds.max_rounds:
            state.rounds += 1
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            thr_in.latency_used_ms = elapsed_ms
            # Round 1: pre-loop compute already ran with latency_used=0; skip recompute.
            if state.rounds > 1:
                thresholds = self.thresholds.compute(thr_in)
                policy.thresholds = thresholds

            node = graph.nodes.get(esc_state.current)
            if node is None:
                break
            if node.kind == "accept":
                break
            if node.kind in {"tool", "memory"}:
                # Signal peers via metadata; ASCR does not own tool/memory execution.
                # Optional ACR connector fills compact context delta when memory_needed.
                if node.kind == "memory" and self.memory_connector is not None:
                    try:
                        query = ""
                        if req.messages:
                            query = str(getattr(req.messages[-1], "content", "") or "")
                        delta = self.memory_connector.on_memory_needed(
                            query or "context",
                            owner=str(getattr(req, "agent_id", "") or "default"),
                        )
                        if delta:
                            state.acr_context_delta = delta
                    except Exception:
                        pass
                # Do not permanently pin mode to quality_cascade — that blocked the
                # logits verify path after HAOE memory prefetch. Memory/tool is a hop.
                edge = self.escalation.next(graph, esc_state)
                if edge is None:
                    break
                esc_state.visited.append(esc_state.current)
                esc_state.current = edge.target
                state.escalations += 1
                continue

            tier_id = int(node.tier_id or 1)
            tier_used = tier_id
            backend_name = self._backend_for_tier(tier_id, policy)

            if use_quality or state.mode == "quality_cascade":
                q_thresh = float(
                    getattr(
                        thresholds,
                        "quality_accept_threshold",
                        thresholds.accept_threshold,
                    )
                )
                result = await self._quality_cascade_tier(
                    req, ctx, backend_name, tier_id, q_thresh
                )
                committed = result.text
                last_verify_text = result.text
                last_backend = result.backend or backend_name
                last_model = result.model or backend_name
                conf = float(result.raw.get("confidence", 0.5))
                esc_state.confidence = conf
                state.last_confidence = conf
                from neuroswarm_arm.runtime.armcascade.confidence.engine import (
                    should_early_accept_quality,
                )

                accept_now = should_early_accept_quality(
                    conf,
                    tier_id=tier_id,
                    threshold=q_thresh,
                    cfg=self.config,
                )
                if accept_now or tier_id >= 3:
                    state.accepted_tokens += approx_tokens(committed)
                    state.mode = "quality_cascade"
                    break
                # Escalate
                esc_state.confidence = conf
                edge = self.escalation.next(graph, esc_state)
                if edge is None:
                    break
                esc_state.visited.append(esc_state.current)
                esc_state.current = edge.target
                state.escalations += 1
                state.mode = "quality_cascade"
                continue

            # --- Speculative propose/verify ---
            if hasattr(proposer, "backend_name") and tier_id == 1:
                proposer.backend_name = policy.draft_backend  # type: ignore[attr-defined]
            if hasattr(verifier, "set_backend"):
                verifier.set_backend(  # type: ignore[attr-defined]
                    policy.verify_backend if tier_id < 3 else policy.escalate_backend
                )

            prop_req = ProposalRequest(
                prompt_text=req.prompt_text,
                messages=build_messages(req.messages, req.system_prompt),
                draft_len=thresholds.draft_len,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                session_id=req.session_id,
                quant=plan.quant,
                kv_handle=getattr(ctx, "kv_handle", None),
                classification=classification,
            )
            try:
                proposal = await proposer.propose(prop_req)
            except NotImplementedError:
                # Stub strategy → degrade to quality cascade.
                state.mode = "quality_cascade"
                use_quality = True
                continue

            state.draft_tokens += proposal.draft_len
            if not proposal.text.strip():
                # Empty draft → quality path on current tier.
                use_quality = True
                continue

            verify_req = VerifyRequest(
                messages=build_messages(req.messages, req.system_prompt),
                prompt_text=req.prompt_text,
                mode=VerifyMode.BLOCK,
                accept_threshold=thresholds.accept_threshold,
                max_tokens=max(thresholds.draft_len, 1),
                temperature=req.temperature,
                session_id=req.session_id,
                quant=plan.quant,
                kv_handle=getattr(ctx, "kv_handle", None),
                verifier_tier=max(2, tier_id),
                batch_size=thresholds.verify_batch_size,
            )
            try:
                vres = await verifier.verify(proposal, verify_req)
            except NotImplementedError:
                use_quality = True
                continue

            state.verifier_calls += 1
            last_verify_text = vres.text or proposal.text
            last_backend = vres.backend or last_backend
            last_model = vres.model or last_model

            if not vres.logits_available and policy.quality_cascade_fallback:
                # Text-agreement interim mode — do not claim true speculative gain.
                text_agree = bool(
                    (self.config or {}).get("text_agree_accept", True)
                )
                if text_agree or vres.agreement < 0.2:
                    state.mode = "text_agree" if vres.agreement >= 0.2 else "quality_cascade"
                last_logits = False
                last_agreement = float(vres.agreement)
            else:
                last_logits = bool(vres.logits_available)
                last_agreement = float(vres.agreement)
                if last_logits:
                    saw_logits = True
                    state.mode = "speculative"

            signals = AcceptanceSignals(
                confidence=0.0,
                agreement=vres.agreement,
                entropy=vres.entropy,
                quality_score=vres.quality_score,
                historical_acceptance=state.historical_acceptance,
                task_kind=classification.task_kind,
                tool_confidence=float(req.tool_confidence or 0.0),
                reasoning_confidence=1.0 - classification.expected_reasoning_depth,
                latency_budget_ms=float(req.latency_sla_ms or 4000.0),
                latency_used_ms=(time.monotonic() - t0) * 1000.0,
                cpu_utilization=telemetry["cpu_utilization"],
                kv_pressure=telemetry["kv_pressure"],
                cache_hit_ratio=telemetry["cache_hit_ratio"],
                draft_len=proposal.draft_len,
                accepted_prefix_len=vres.accepted_prefix_len,
                accept_threshold=thresholds.accept_threshold,
                escalate_threshold=thresholds.escalate_threshold,
                is_terminal_tier=tier_id >= 3 or node.kind == "accept",
            )
            decision = self.acceptance.decide(signals)
            esc_state.confidence = signals.confidence or self.confidence.fuse(signals)
            state.last_confidence = esc_state.confidence

            if decision.action == AcceptanceAction.ACCEPT:
                prefix = _prefix_text(proposal.text, decision.accepted_prefix_len) or last_verify_text
                committed = (committed + " " + prefix).strip() if committed else prefix
                state.accepted_tokens += decision.accepted_prefix_len or approx_tokens(prefix)
                break

            if decision.action == AcceptanceAction.PARTIAL_ACCEPT:
                prefix = _prefix_text(proposal.text, decision.accepted_prefix_len)
                if prefix:
                    committed = (committed + " " + prefix).strip() if committed else prefix
                    state.accepted_tokens += decision.accepted_prefix_len
                # Continue with remaining generation via quality on verify tier.
                use_quality = True
                esc_state.current = "tier2" if "tier2" in graph.nodes else esc_state.current
                continue

            if decision.action == AcceptanceAction.INCREASE_SPECULATION:
                thresholds.draft_len = min(48, thresholds.draft_len + max(1, decision.adjust_draft_delta))
                continue

            if decision.action == AcceptanceAction.REDUCE_SPECULATION:
                thresholds.draft_len = max(2, thresholds.draft_len + min(-1, decision.adjust_draft_delta))
                continue

            if decision.action in {AcceptanceAction.REJECT, AcceptanceAction.ESCALATE}:
                state.rejected_tokens += max(0, proposal.draft_len - vres.accepted_prefix_len)
                edge = self.escalation.next(graph, esc_state)
                if edge is None:
                    committed = committed or last_verify_text or proposal.text
                    break
                esc_state.visited.append(esc_state.current)
                esc_state.current = edge.target
                state.escalations += 1
                if edge.target == "accept":
                    committed = committed or last_verify_text or proposal.text
                    break
                continue

        if not committed:
            # Final fallback: full generate on escalate backend.
            committed = await self._final_generate(
                req, ctx, policy.escalate_backend, plan.quant
            )
            last_backend = policy.escalate_backend
            tier_used = 3
            # Keep speculative label if a verify round already saw logits.
            if not saw_logits:
                state.mode = "quality_cascade"

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        accept_rate = state.accepted_tokens / max(1, state.accepted_tokens + state.rejected_tokens)
        self._history_accept = 0.8 * self._history_accept + 0.2 * accept_rate

        if saw_logits and state.mode != "quality_cascade":
            state.mode = "speculative"

        self.metrics.record_round(
            accepted_tokens=state.accepted_tokens or approx_tokens(committed),
            rejected_tokens=state.rejected_tokens,
            draft_tokens=state.draft_tokens or approx_tokens(committed),
            latency_ms=elapsed_ms,
            tier_used=tier_used,
            mode=state.mode,
            numa_locality=placement.locality,
            cpu=telemetry["cpu_utilization"],
            cache_hit=telemetry["cache_hit_ratio"],
            kv_reuse=float(getattr(ctx, "kv_reuse", 0.0) or 0.0),
            logits_available=saw_logits and state.mode == "speculative",
            text_agreement=last_agreement,
        )
        self.performix.record(
            {
                "ascr_latency_ms": elapsed_ms,
                "ascr_tier": float(tier_used),
                "ascr_confidence": state.last_confidence,
                "ascr_accept_rate": accept_rate,
            }
        )
        self._emit(
            "ascr_complete",
            {
                "tier_used": float(tier_used),
                "confidence": state.last_confidence,
                "latency_ms": elapsed_ms,
                "rounds": float(state.rounds),
            },
        )

        return GenerateResult(
            text=committed,
            prompt_tokens=approx_tokens(req.prompt_text),
            completion_tokens=approx_tokens(committed),
            latency_ms=elapsed_ms,
            ttft_ms=elapsed_ms * 0.2,
            backend=last_backend,
            model=last_model,
            quant=plan.quant,
            tier_used=tier_used,
            raw={
                "confidence": state.last_confidence,
                "ascr_mode": state.mode,
                "ascr_rounds": state.rounds,
                "ascr_strategy": policy.proposal_strategy,
                "ascr_verify": policy.verify_strategy,
                "ascr_graph": policy.graph_name,
                "logits_available": saw_logits,
            },
            metrics={
                "confidence": state.last_confidence,
                "escalated": 1.0 if state.escalations else 0.0,
                "cascade_latency_ms": elapsed_ms,
                "ascr_draft_tokens": float(state.draft_tokens),
                "ascr_accepted_tokens": float(state.accepted_tokens),
                "ascr_rejected_tokens": float(state.rejected_tokens),
                # Honesty: gain is 0 outside true speculative mode (quality accepts
                # must not be reported as speculation_gain).
                "ascr_speculation_gain": (
                    0.0
                    if state.mode in {"quality_cascade", "text_agree"}
                    else float(
                        self.metrics.snapshot().get("ascr_speculation_gain", 0.0)
                    )
                ),
                "logits_available": 1.0 if saw_logits else 0.0,
                "ascr_mode": state.mode,
            },
        )

    def _get_proposer(self, policy: PolicyDecision) -> ProposalStrategy:
        try:
            return self.proposers.get(policy.proposal_strategy)
        except KeyError:
            return self.proposers.get("draft_model")

    def _get_verifier(self, policy: PolicyDecision) -> VerifierStrategy:
        try:
            return self.verifiers.get(policy.verify_strategy)
        except KeyError:
            return self.verifiers.get("block")

    async def _bind_strategies(
        self,
        proposer: ProposalStrategy,
        verifier: VerifierStrategy,
        ctx: ExecutionContext,
    ) -> None:
        init = ASCRInitContext(
            registry=self.registry,
            config=self.config,
            metrics=self.metrics,
            arm=self.arm,
        )
        await proposer.initialize(init)
        await verifier.initialize(init)
        if hasattr(proposer, "bind_execution_context"):
            proposer.bind_execution_context(ctx)  # type: ignore[attr-defined]
        if hasattr(verifier, "bind_execution_context"):
            verifier.bind_execution_context(ctx)  # type: ignore[attr-defined]

    def _backend_for_tier(self, tier_id: int, policy: PolicyDecision) -> str:
        if tier_id <= 1:
            return policy.draft_backend
        if tier_id == 2:
            return policy.verify_backend
        return policy.escalate_backend

    async def _quality_cascade_tier(
        self,
        req: InferenceRequest,
        ctx: ExecutionContext,
        backend_name: str,
        tier_id: int,
        threshold: float,
    ) -> GenerateResult:
        from neuroswarm_arm.runtime.armcascade.confidence.engine import text_quality_score

        backend = self.registry.require(backend_name)
        gen = GenerateRequest(
            messages=build_messages(req.messages, req.system_prompt),
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            session_id=req.session_id,
            quant=getattr(ctx, "quant", "") or "",
            stream=False,
            kv_handle=getattr(ctx, "kv_handle", None),
            speculative=False,
        )
        result = await backend.generate(gen, ctx)
        conf = text_quality_score(result.text, self.config.get("confidence"))
        return GenerateResult(
            text=result.text,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens or approx_tokens(result.text),
            latency_ms=result.latency_ms,
            ttft_ms=result.ttft_ms,
            backend=result.backend or backend_name,
            model=result.model or backend_name,
            quant=result.quant,
            tier_used=tier_id,
            raw={**result.raw, "confidence": conf, "threshold": threshold},
            metrics=dict(result.metrics),
        )

    async def _final_generate(
        self,
        req: InferenceRequest,
        ctx: ExecutionContext,
        backend_name: str,
        quant: str,
    ) -> str:
        backend = self.registry.require(backend_name)
        gen = GenerateRequest(
            messages=build_messages(req.messages, req.system_prompt),
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            session_id=req.session_id,
            quant=quant,
            stream=False,
            kv_handle=getattr(ctx, "kv_handle", None),
        )
        result = await backend.generate(gen, ctx)
        return result.text

    def _emit(self, event: str, fields: Mapping[str, float]) -> None:
        if self.legacy_metrics is not None:
            self.legacy_metrics(event, fields)
        self.metrics.emit_event(event, fields)


def _prefix_text(text: str, n_tokens: int) -> str:
    if n_tokens <= 0 or not text.strip():
        return ""
    words = text.split()
    return " ".join(words[:n_tokens])
