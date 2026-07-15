"""RTGRuntime — Reasoning Token Governor peer kernel (AIM Pillar 4)."""

from __future__ import annotations

from typing import Any, Mapping

from .config import RTGRuntimeConfig
from .control import (
    BudgetAllocator,
    DecisionEngine,
    EarlyExitEngine,
    RuntimeController,
    StreamingController,
    SwarmBudgetManager,
)
from .estimators import AnswerStabilityEstimator, BudgetPredictor, ReasoningROIEstimator
from .events import EventBus
from .models import BudgetEnvelope, Decision, GovernorAction, TelemetryFrame
from .policy import PolicyEngine
from .sensors import (
    ComplexityEstimator,
    ConfidenceEstimator,
    EntropyMonitor,
    KVPressureSensor,
    LatencySLOSensor,
    PlateauDetector,
    SelfConsistencyMonitor,
    SemanticSensor,
)
from .telemetry import HardwareMonitor, MetricsCollector, OpenTelemetryAdapter


class RTGRuntime:
    """OS-style reasoning control plane over DIPA decode."""

    def __init__(
        self,
        config: RTGRuntimeConfig,
        *,
        streaming: StreamingController,
        allocator: BudgetAllocator,
        policy: PolicyEngine,
        metrics: MetricsCollector,
        events: EventBus,
        hardware: HardwareMonitor,
        otel: OpenTelemetryAdapter,
        swarm: SwarmBudgetManager,
        controller: RuntimeController,
        early_exit: EarlyExitEngine,
    ) -> None:
        self.config = config
        self.streaming = streaming
        self.allocator = allocator
        self.policy = policy
        self.metrics = metrics
        self.events = events
        self.hardware = hardware
        self.otel = otel
        self.swarm = swarm
        self.controller = controller
        self.early_exit = early_exit

    def initial_budget(self, frame: TelemetryFrame | Mapping[str, Any] | Any) -> int:
        tf = self._as_frame(frame)
        tf = self.hardware.apply_to_frame(tf)
        # Run complexity sensor for TALE prediction
        state_probe = self.streaming.controller.get(tf.session_id)
        from .models import SessionState

        st = state_probe or SessionState(session_id=tf.session_id or "probe")
        for sensor in self.streaming.sensors:
            if getattr(sensor, "name", "") in {"complexity", "semantic", "kv_pressure", "latency_slo"}:
                tf = sensor.observe(tf, st)
        env = self.allocator.initial_budget(tf)
        return int(env.initial_tokens)

    def initial_envelope(self, frame: TelemetryFrame | Mapping[str, Any] | Any) -> BudgetEnvelope:
        tf = self._as_frame(frame)
        tf = self.hardware.apply_to_frame(tf)
        from .models import SessionState

        st = SessionState(session_id=tf.session_id or "probe")
        for sensor in self.streaming.sensors:
            if getattr(sensor, "name", "") in {"complexity", "semantic", "kv_pressure", "latency_slo"}:
                tf = sensor.observe(tf, st)
        return self.allocator.initial_budget(tf)

    def prompt(self, cap: int) -> str:
        template = (self.config.policy.get("prompt_template") or "").strip()
        if not template:
            template = (
                "You may reason for up to {cap} tokens before producing a tool call. "
                "If your chosen tool confidence is >= 0.85, commit immediately."
            )
        return template.format(cap=cap)

    def admit(self, frame: TelemetryFrame | Mapping[str, Any] | Any) -> Any:
        tf = self._as_frame(frame)
        tf = self.hardware.apply_to_frame(tf)
        with self.otel.span("rtg.admit", session_id=tf.session_id):
            return self.streaming.on_admit(tf)

    def on_chunk(self, session_id: str, chunk_text: str, **kwargs: Any) -> Decision:
        with self.otel.span("rtg.chunk", session_id=session_id):
            return self.streaming.on_chunk(session_id, chunk_text, **kwargs)

    def on_complete(self, session_id: str, final_text: str = "") -> Decision:
        with self.otel.span("rtg.complete", session_id=session_id):
            return self.streaming.on_complete(session_id, final_text)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "sessions": len(self.controller.sessions),
            "bandit_enabled": self.config.bandit_enabled,
            "swarm_enabled": self.config.swarm_enabled,
            "ppo_enabled": self.config.ppo_enabled,
            "metrics": dict(self.metrics.gauges),
        }

    @staticmethod
    def _as_frame(frame: TelemetryFrame | Mapping[str, Any] | Any) -> TelemetryFrame:
        if isinstance(frame, TelemetryFrame):
            return frame
        if isinstance(frame, Mapping):
            fields = {k: v for k, v in frame.items() if k in TelemetryFrame.__dataclass_fields__}
            return TelemetryFrame(**fields)
        return TelemetryFrame.from_plan_state(frame)
