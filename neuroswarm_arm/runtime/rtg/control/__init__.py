"""RTG control plane — allocate, stream, decide, swarm."""

from __future__ import annotations

import time
from typing import Any

from ..config import RTGRuntimeConfig
from ..estimators import (
    AnswerStabilityEstimator,
    BudgetPredictor,
    ReasoningROIEstimator,
    build_envelope,
)
from ..events import EventBus
from ..interfaces import IBudgetAllocator, IStreamingController
from ..models import (
    BudgetEnvelope,
    Decision,
    GovernorAction,
    SessionPhase,
    SessionState,
    TelemetryFrame,
)
from ..policy import PolicyEngine
from ..sensors import (
    ComplexityEstimator,
    ConfidenceEstimator,
    EntropyMonitor,
    KVPressureSensor,
    LatencySLOSensor,
    PlateauDetector,
    SelfConsistencyMonitor,
    SemanticSensor,
)


class BudgetAllocator(IBudgetAllocator):
    def __init__(self, cfg: RTGRuntimeConfig, predictor: BudgetPredictor) -> None:
        self.cfg = cfg
        self.predictor = predictor

    def initial_budget(self, frame: TelemetryFrame) -> BudgetEnvelope:
        tokens = self.predictor.predict_tokens(frame)
        # L0 pressure scales before streaming
        if frame.kv_pressure > self.cfg.kv_pressure_soft:
            tokens = min(tokens, 512)
        if frame.memory_pressure > self.cfg.memory_pressure_hard:
            tokens = min(tokens, 256)
        if frame.tool_confidence_top1 > self.cfg.tool_confidence_commit:
            tokens = min(tokens, 256)
        if frame.self_consistency_score > self.cfg.self_consistency_commit:
            tokens = min(tokens, 128)
        if (
            float(getattr(frame, "latency_spent_ms", 0.0) or 0.0) > 0
            and frame.slo_remaining_ms < self.cfg.slo_soft_ms
        ):
            tokens = min(tokens, int(256 + 4 * frame.tool_confidence_top1 * 1024))
        if frame.kv_hit_rate < 0.20 and frame.kv_pressure > 0.50:
            tokens = min(tokens, 384)
        if frame.kv_migration_latency_ms > 50.0:
            tokens = min(tokens, 512)
        tokens = int(max(self.cfg.min_budget, min(self.cfg.max_budget, tokens)))
        return build_envelope(self.cfg, tokens, frame)

    def next_chunk(self, state: SessionState) -> int:
        rem = state.budget.remaining_tokens
        base = state.budget.chunk_size or self.cfg.chunk_size
        # Grow chunk when confidence rising slowly; shrink near SLO
        conf_delta = 0.0
        if len(state.confidence_history) >= 2:
            conf_delta = state.confidence_history[-1] - state.confidence_history[-2]
        scale = 1.0 + max(-0.5, min(0.5, conf_delta * 2))
        if state.frame.slo_remaining_ms < 1500:
            scale *= 0.5
        return int(max(16, min(rem, round(base * scale))))


class BudgetReallocator:
    def apply(self, state: SessionState, decision: Decision) -> BudgetEnvelope:
        budget = state.budget
        if decision.new_budget is not None:
            budget.remaining_tokens = int(
                max(budget.min_tokens, min(budget.max_tokens, decision.new_budget))
            )
        elif decision.budget_delta:
            budget.apply_delta(decision.budget_delta)
        if decision.action == GovernorAction.INCREASE_BUDGET and not decision.budget_delta:
            budget.apply_delta(budget.chunk_size)
        if decision.action == GovernorAction.DECREASE_BUDGET and not decision.budget_delta and decision.new_budget is None:
            budget.apply_delta(-budget.chunk_size)
        return budget


class EarlyExitEngine:
    def should_force_close(self, decision: Decision) -> bool:
        return bool(decision.force_close or decision.terminal)


class SwarmBudgetManager:
    """Water-filling across active sessions by priority × need / cost."""

    def __init__(self, cfg: RTGRuntimeConfig) -> None:
        self.cfg = cfg
        self._sessions: dict[str, SessionState] = {}

    def register(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state

    def unregister(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def rebalance(self) -> dict[str, int]:
        if not self.cfg.swarm_enabled or len(self._sessions) < 2:
            return {}
        # Redistribute only existing remaining pool — never inflate budgets.
        pool = float(
            min(
                self.cfg.swarm_global_tokens,
                sum(st.budget.remaining_tokens for st in self._sessions.values()),
            )
        )
        weights: dict[str, float] = {}
        for sid, st in self._sessions.items():
            need = max(0.05, 1.0 - (st.frame.confidence_ema or st.frame.model_confidence))
            cost = max(1e-6, st.budget.cost_spent_usd + 1e-4)
            weights[sid] = max(0.01, st.frame.agent_priority * need / cost)
        total_w = sum(weights.values()) or 1.0
        alloc = {sid: int(pool * (w / total_w)) for sid, w in weights.items()}
        for sid, tokens in alloc.items():
            st = self._sessions[sid]
            st.budget.remaining_tokens = int(
                min(
                    st.budget.initial_tokens,
                    st.budget.max_tokens,
                    max(st.budget.min_tokens, tokens),
                )
            )
        return alloc


class DecisionEngine:
    def __init__(self, policy: PolicyEngine, reallocator: BudgetReallocator | None = None) -> None:
        self.policy = policy
        self.reallocator = reallocator or BudgetReallocator()

    def decide(self, frame: TelemetryFrame, state: SessionState) -> Decision:
        decision = self.policy.decide(frame, state)
        self.reallocator.apply(state, decision)
        state.decisions.append(decision)
        state.last_action = decision.action
        return decision


class RuntimeController:
    """Session lifecycle for RTG."""

    def __init__(self) -> None:
        self.sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState | None:
        return self.sessions.get(session_id)

    def put(self, state: SessionState) -> None:
        self.sessions[state.session_id] = state

    def pop(self, session_id: str) -> SessionState | None:
        return self.sessions.pop(session_id, None)


class StreamingController(IStreamingController):
    def __init__(
        self,
        cfg: RTGRuntimeConfig,
        *,
        allocator: BudgetAllocator,
        decision_engine: DecisionEngine,
        sensors: list[Any],
        estimators: list[Any],
        swarm: SwarmBudgetManager | None = None,
        events: EventBus | None = None,
        metrics: Any | None = None,
        early_exit: EarlyExitEngine | None = None,
        controller: RuntimeController | None = None,
    ) -> None:
        self.cfg = cfg
        self.allocator = allocator
        self.decision_engine = decision_engine
        self.sensors = sensors
        self.estimators = estimators
        self.swarm = swarm
        self.events = events or EventBus()
        self.metrics = metrics
        self.early_exit = early_exit or EarlyExitEngine()
        self.controller = controller or RuntimeController()

    def on_admit(self, frame: TelemetryFrame) -> SessionState:
        enriched = self._enrich(frame, SessionState(session_id=frame.session_id or f"rtg-{id(frame)}"))
        budget = self.allocator.initial_budget(enriched)
        sid = enriched.session_id or f"sess-{int(time.time() * 1000)}"
        enriched.session_id = sid
        state = SessionState(
            session_id=sid,
            phase=SessionPhase.ALLOCATE,
            budget=budget,
            frame=enriched,
            started_ms=time.time() * 1000.0,
        )
        state.phase = SessionPhase.STREAMING
        self.controller.put(state)
        if self.swarm:
            self.swarm.register(state)
            self.swarm.rebalance()
        self.events.publish(
            "rtg.admit",
            {"session_id": sid, "budget": budget.initial_tokens, "complexity": enriched.complexity_score},
        )
        if self.metrics:
            self.metrics.on_admit(budget.initial_tokens)
        return state

    def on_chunk(self, session_id: str, chunk_text: str, **kwargs: Any) -> Decision:
        state = self.controller.get(session_id)
        if state is None:
            frame = TelemetryFrame(session_id=session_id, chunk_text=chunk_text, **{
                k: v for k, v in kwargs.items() if k in TelemetryFrame.__dataclass_fields__
            })
            state = self.on_admit(frame)
        tokens = int(kwargs.get("tokens", max(1, len(chunk_text.split()))))
        latency_ms = float(kwargs.get("latency_ms", 0.0))
        state.budget.consume(
            tokens,
            latency_ms=latency_ms,
            cost_usd=(tokens / 1000.0) * self.cfg.cost_per_1k_tokens,
        )
        state.frame.chunk_text = chunk_text
        state.frame.accumulated_text = (state.frame.accumulated_text + chunk_text)[-8000:]
        state.frame.thinking_tokens_so_far += tokens
        state.frame.completion_tokens_so_far += tokens
        state.frame.energy_so_far_joules += tokens * self.cfg.watts_per_token
        state.frame.cost_so_far_usd = state.budget.cost_spent_usd
        for k, v in kwargs.items():
            if hasattr(state.frame, k) and k not in {"chunk_text"}:
                try:
                    setattr(state.frame, k, v)
                except Exception:  # noqa: BLE001
                    pass
        state.frame = self._enrich(state.frame, state)
        state.text_history.append(state.frame.accumulated_text[-500:])
        decision = self.decision_engine.decide(state.frame, state)
        self.events.publish(
            "rtg.decision",
            {
                "session_id": session_id,
                "action": decision.action.value,
                "reason": decision.reason,
                "remaining": state.budget.remaining_tokens,
            },
        )
        if self.metrics:
            self.metrics.on_decision(decision, state)
        if decision.terminal:
            state.phase = SessionPhase.FINALIZE
        return decision

    def on_complete(self, session_id: str, final_text: str = "") -> Decision:
        state = self.controller.get(session_id)
        if state is None:
            return Decision(action=GovernorAction.CONTINUE, reason="no_session")
        if final_text:
            state.frame.accumulated_text = final_text
            state.frame = self._enrich(state.frame, state)
        # Bandit feedback
        bandit = getattr(self.decision_engine.policy, "bandit", None)
        if bandit is not None and hasattr(bandit, "feedback"):
            used = state.budget.initial_tokens - state.budget.remaining_tokens
            bandit.feedback(session_id, state.frame, used)
        decision = Decision(
            action=state.last_action if state.last_action != GovernorAction.CONTINUE else GovernorAction.EARLY_COMMIT,
            reason="complete",
            policy_layer="runtime",
        )
        state.phase = SessionPhase.DONE
        if self.swarm:
            self.swarm.unregister(session_id)
        if self.metrics:
            self.metrics.on_complete(state)
        self.events.publish("rtg.complete", {"session_id": session_id, "tokens": state.frame.thinking_tokens_so_far})
        self.controller.pop(session_id)
        return decision

    def _enrich(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        for sensor in self.sensors:
            frame = sensor.observe(frame, state)
        for est in self.estimators:
            frame = est.estimate(frame, state)
        return frame
