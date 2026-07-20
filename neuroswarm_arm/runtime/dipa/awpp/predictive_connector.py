"""Predictive AWPP warm connector — predictors + warmers on the DIPA hot path."""

from __future__ import annotations

from typing import Any, Mapping

from neuroswarm_arm.runtime.acr.connectors.awpp import ACRPrefetchPredictor
from neuroswarm_arm.runtime.awpp.actions import AWPPAction, WarmTarget, WarmTargetKind
from neuroswarm_arm.runtime.awpp.confidence import gate
from neuroswarm_arm.runtime.awpp.config import AWPPRuntimeConfig, load_awpp_config
from neuroswarm_arm.runtime.awpp.interfaces import (
    IPolicy,
    IPredictor,
    Prediction,
    PrewarmBudget,
)
from neuroswarm_arm.runtime.awpp.memory_predictor import MemoryPrefetchPredictor
from neuroswarm_arm.runtime.awpp.metrics import AWPPMetrics
from neuroswarm_arm.runtime.awpp.observation import Observation
from neuroswarm_arm.runtime.awpp.policy import build_policy
from neuroswarm_arm.runtime.awpp.replay import ReplayWriter
from neuroswarm_arm.runtime.awpp.state import AWPPState
from neuroswarm_arm.runtime.awpp.warmers import (
    MemoryWarmer,
    ModelWarmer,
    ToolWarmer,
    WarmerDispatcher,
)
from neuroswarm_arm.runtime.dipa.awpp.warm_connector import HeuristicWarmConnector
from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan, InferenceRequest
from neuroswarm_arm.runtime.dipa.interfaces.warm import IWarmConnector


class PredictiveWarmConnector(IWarmConnector):
    """Layer-4 predictive pre-warm: ACR/Mem predictors + frequency/Markov + warmers.

    Falls back to :class:`HeuristicWarmConnector` when prediction is skipped or fails.
    """

    def __init__(
        self,
        *,
        config: AWPPRuntimeConfig | None = None,
        predictor: IPredictor | None = None,
        policy: IPolicy | None = None,
        metrics: AWPPMetrics | None = None,
        maks: Any | None = None,
        memory: Any | None = None,
        tool_router: Any | None = None,
        acr: Any | None = None,
        dispatcher: WarmerDispatcher | None = None,
        heuristic: HeuristicWarmConnector | None = None,
    ) -> None:
        self.config = config or load_awpp_config()
        self.metrics = metrics or AWPPMetrics()
        self._maks = maks
        self._memory = memory
        self._tool_router = tool_router
        self._acr = acr
        self._heuristic = heuristic or HeuristicWarmConnector(maks=maks)
        self._warm: set[str] = set()
        self.model_warm_state: dict[str, bool] = {}
        self.last_prediction: str | None = None
        self.last_policy_id: str = ""
        self.last_confidence: float = 0.0
        self._last_action: AWPPAction | None = None
        self._cold_before: dict[str, bool] = {}

        self.replay = ReplayWriter(self.config.replay_dir or self.config.root / "replay")
        self.policy = policy or build_policy(
            self.config.active_policy,
            min_observations=3,
        )
        if self.config.policy_path:
            try:
                self.policy.load(self.config.policy_path)
            except Exception:
                pass

        self.predictor: IPredictor = predictor or ACRPrefetchPredictor(
            acr=acr, memory=memory
        )
        # Keep a direct memory predictor for update() fan-out
        self._memory_predictor = MemoryPrefetchPredictor(memory=memory)

        model_warmer = ModelWarmer(urls=self.config.warmup_urls)
        memory_warmer = MemoryWarmer(memory=memory)
        tool_warmer = ToolWarmer(router=tool_router)
        budget = PrewarmBudget(
            max_concurrent=self.config.max_concurrent_warms,
            max_memory_bytes=self.config.max_memory_bytes,
            max_cpu_fraction=self.config.max_cpu_fraction,
            timeout_s=self.config.warm_timeout_s,
            rate_limit_per_s=self.config.rate_limit_per_s,
        )
        self.dispatcher = dispatcher or WarmerDispatcher(
            {
                "model": model_warmer,
                "memory": memory_warmer,
                "tool": tool_warmer,
            },
            budget=budget,
            metrics=self.metrics,
        )
        self._model_warmer = model_warmer
        self._memory_warmer = memory_warmer
        self._tool_warmer = tool_warmer

    def bind_maks(self, maks: Any) -> None:
        self._maks = maks
        self._heuristic.bind_maks(maks)

    def bind_runtime(
        self,
        *,
        memory: Any | None = None,
        tool_router: Any | None = None,
        acr: Any | None = None,
    ) -> None:
        if memory is not None:
            self._memory = memory
            self._memory_warmer.bind(memory)
            self._memory_predictor.memory = memory
            if isinstance(self.predictor, ACRPrefetchPredictor):
                self.predictor._fallback.memory = memory  # noqa: SLF001
        if tool_router is not None:
            self._tool_router = tool_router
            self._tool_warmer.bind(tool_router)
        if acr is not None:
            self._acr = acr
            if isinstance(self.predictor, ACRPrefetchPredictor):
                self.predictor.acr = acr

    def build_state(
        self, req: InferenceRequest, plan: ExecutionPlan, *, hints: Mapping[str, Any] | None = None
    ) -> AWPPState:
        hints = dict(hints or {})
        prompt = req.prompt_text[:256]
        last_tools = list(req.tool_names or [])
        if req.baggage.get("last_tools"):
            last_tools = list(req.baggage.get("last_tools") or last_tools)
        return AWPPState(
            agent_id=str(req.agent_id or "default"),
            session_id=str(req.session_id or ""),
            workflow_id=str(req.baggage.get("workflow_id") or ""),
            current_node=str(plan.model or req.model or ""),
            latency_slo_ms=float(req.latency_sla_ms or self.config.latency_slo_ms),
            horizon_s=float(self.config.horizon_s),
            metadata={
                "prompt_excerpt": prompt,
                "agent_role": req.agent_role,
                "last_tools": last_tools,
                "last_model": str(req.baggage.get("last_model") or ""),
                "last_tool": str(last_tools[-1] if last_tools else ""),
                "plan_model": plan.model,
                **hints,
            },
        )

    def _predict(self, state: AWPPState) -> Prediction:
        # Prefer frequency/Markov policy when it has history; else ACR/Mem predictors
        policy_pred = self.policy.act(state)
        if not policy_pred.action.skip and policy_pred.confidence > 0.0:
            pred = policy_pred
        else:
            try:
                pred = self.predictor.predict(state)
            except Exception:
                pred = Prediction(
                    action=AWPPAction(skip=True),
                    confidence=0.0,
                    entropy=1.0,
                    uncertainty=1.0,
                    policy_id="predictor_error",
                )
        # Ensure planned model is always a warm target when always_warm_tier1 / plan known
        model = str(state.metadata.get("plan_model") or state.current_node or "")
        if model and self.config.always_warm_tier1:
            targets = list(pred.action.all_targets())
            if not any(t.kind == WarmTargetKind.MODEL and t.key == model for t in targets):
                targets.insert(0, WarmTarget(WarmTargetKind.MODEL, model, max(pred.confidence, 0.5)))
            pred.action.targets = targets
            pred.action.next_model = pred.action.next_model or model
            pred.action.skip = False
        return pred

    async def ensure_warm(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        *,
        hints: Mapping[str, Any] | None = None,
    ) -> bool:
        model = plan.model or req.model
        was_warm = model in self._warm or self._heuristic.is_warm(model)
        self._cold_before[req.session_id or model] = not was_warm

        try:
            state = self.build_state(req, plan, hints=hints)
            pred = self._predict(state)
            skipped = (not gate(pred.confidence, self.config.confidence_threshold)) or pred.action.skip
            self.metrics.observe_prediction(
                confidence=pred.confidence,
                entropy=pred.entropy,
                uncertainty=pred.uncertainty,
                skipped=skipped,
            )
            self.last_confidence = pred.confidence
            self.last_policy_id = pred.policy_id or getattr(self.policy, "policy_id", "")
            self._last_action = pred.action

            if skipped:
                # Heuristic fallback still marks planned model
                await self._heuristic.ensure_warm(req, plan, hints=hints)
                self._warm.add(model)
                self.model_warm_state[model] = True
                self.last_prediction = model
                self._annotate(req, plan, prediction=model)
                return True

            targets = pred.action.all_targets()
            primary = pred.action.next_model or model
            self.last_prediction = primary
            results = await self.dispatcher.dispatch(
                targets,
                metadata={
                    "agent_id": req.agent_id,
                    "query": req.prompt_text[:256],
                    "session_id": req.session_id,
                },
            )
            for r in results:
                if r.success and r.target_kind == "model":
                    self._warm.add(r.target_key)
                    self.model_warm_state[r.target_key] = True

            # Always ensure planned model + optional MAKS KV via heuristic
            await self._heuristic.ensure_warm(req, plan, hints=hints)
            self._warm.add(model)
            self.model_warm_state[model] = True
            self._annotate(req, plan, prediction=primary)
            return True
        except Exception:
            await self._heuristic.ensure_warm(req, plan, hints=hints)
            self._warm.add(model)
            self.model_warm_state[model] = True
            self.last_prediction = model
            self._annotate(req, plan, prediction=model)
            return True

    def _annotate(self, req: InferenceRequest, plan: ExecutionPlan, *, prediction: str) -> None:
        """Fill AQR / baggage fields so WarmBonusExtractor is not dead."""
        req.baggage["awpp_prediction"] = prediction
        req.baggage["model_warm_state"] = dict(self.model_warm_state)
        req.baggage["awpp_policy"] = self.last_policy_id
        req.baggage["awpp_confidence"] = self.last_confidence
        plan.metadata["awpp_prediction"] = prediction
        plan.metadata["model_warm_state"] = dict(self.model_warm_state)
        plan.metadata["awpp_policy"] = self.last_policy_id

    def populate_aqr_context(self, ctx: Any) -> None:
        """Copy warm signals onto an AQR RequestContext instance."""
        if hasattr(ctx, "awpp_prediction"):
            ctx.awpp_prediction = self.last_prediction
        if hasattr(ctx, "model_warm_state"):
            warm = getattr(ctx, "model_warm_state", None)
            if isinstance(warm, dict):
                warm.update(self.model_warm_state)
            else:
                ctx.model_warm_state = dict(self.model_warm_state)

    async def prefetch(self, model: str, session_id: str = "") -> None:
        await self.dispatcher.dispatch(
            [WarmTarget(WarmTargetKind.MODEL, model, 1.0)],
            metadata={"session_id": session_id},
        )
        await self._heuristic.prefetch(model, session_id)
        self._warm.add(model)
        self.model_warm_state[model] = True

    def is_warm(self, model: str) -> bool:
        return model in self._warm or self._heuristic.is_warm(model) or self._model_warmer.is_warm(model)

    def record_observation(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        *,
        latency_ms: float = 0.0,
        tools_used: list[str] | None = None,
        model: str | None = None,
        cold_start: bool | None = None,
    ) -> Observation:
        """Emit observation for policy update + replay JSONL."""
        used_model = model or plan.model or req.model
        tools = list(tools_used or req.tool_names or [])
        was_cold = (
            self._cold_before.pop(req.session_id or used_model, False)
            if cold_start is None
            else cold_start
        )
        obs = Observation(
            agent_id=str(req.agent_id or "default"),
            session_id=str(req.session_id or ""),
            event_type="inference_complete",
            model=str(used_model or ""),
            quant=str(plan.quant or ""),
            tool=str(tools[0] if tools else ""),
            backend=str(plan.backend or ""),
            cascade_tier=int(plan.cascade_start_tier or 0),
            latency_ms=float(latency_ms),
            cold_start=bool(was_cold),
            cache_hit=not was_cold,
            cache_miss=bool(was_cold),
            metadata={
                "tools": tools,
                "awpp_prediction": self.last_prediction,
                "awpp_policy": self.last_policy_id,
            },
        )
        try:
            self.policy.update(obs)
        except Exception:
            pass
        try:
            self.predictor.update(obs)
        except Exception:
            pass
        try:
            self._memory_predictor.update(obs)
        except Exception:
            pass
        pred_meta = {
            "next_model": getattr(self._last_action, "next_model", "") if self._last_action else "",
            "next_tool": getattr(self._last_action, "next_tool", "") if self._last_action else "",
            "confidence": self.last_confidence,
            "policy_id": self.last_policy_id,
        }
        try:
            self.replay.append(obs, prediction=pred_meta)
        except Exception:
            pass
        # Accuracy: predicted model used?
        if self.last_prediction:
            correct = self.last_prediction == used_model or self.last_prediction in {
                t for t in tools
            }
            self.metrics.record_accuracy(bool(correct))
            if was_cold and not correct:
                self.metrics.inc("awpp_false_negatives_total")
            if (not was_cold) and self.last_prediction and self.last_prediction != used_model:
                self.metrics.inc("awpp_false_positives_total")
        req.baggage["last_model"] = used_model
        if tools:
            req.baggage["last_tools"] = tools
        return obs

    def status(self) -> dict[str, Any]:
        snap = self.metrics.snapshot()
        disp = self.dispatcher.status()
        return {
            "policy": self.last_policy_id or getattr(self.policy, "policy_id", self.config.active_policy),
            "active_policy": self.config.active_policy,
            "confidence_threshold": self.config.confidence_threshold,
            "max_cpu_fraction": self.config.max_cpu_fraction,
            "last_prediction": self.last_prediction,
            "last_confidence": self.last_confidence,
            "warm_hits": disp.get("warm_hits", 0),
            "skips": disp.get("skips_total", 0),
            "model_warm_state": dict(self.model_warm_state),
            "metrics": snap,
            "dispatcher": disp,
        }
