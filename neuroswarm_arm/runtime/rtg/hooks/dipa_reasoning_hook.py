"""DIPA-facing reasoning hook — RTG implements IReasoningHook without DIPA importing RTG."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import Decision, GovernorAction, TelemetryFrame

if TYPE_CHECKING:
    from ..kernel import RTGRuntime


class DIPAReasoningHook:
    """Adapter that satisfies neuroswarm_arm.runtime.dipa.interfaces.reasoning.IReasoningHook."""

    def __init__(self, rtg: RTGRuntime, memory: Any | None = None) -> None:
        self.rtg = rtg
        self.memory = memory
        self._session_map: dict[str, str] = {}
        self._agent_by_session: dict[str, str] = {}

    def on_admit(self, request: Any, **kwargs: Any) -> dict[str, Any]:
        frame = self._frame_from_request(request, **kwargs)
        state = self.rtg.admit(frame)
        self._session_map[frame.session_id] = state.session_id
        self._agent_by_session[state.session_id] = frame.agent_id or "default"
        cap = state.budget.initial_tokens
        return {
            "session_id": state.session_id,
            "thinking_token_cap": cap,
            "system_prompt": self.rtg.prompt(cap),
            "governor_accuracy_demand": float(
                1.0 - frame.tool_confidence_top1 if frame.complexity_score > 0.5 else 0.4
            ),
            "force_close_message": self.rtg.config.force_close_message,
        }

    def on_chunk(self, session_id: str, chunk_text: str, **kwargs: Any) -> dict[str, Any]:
        decision = self.rtg.on_chunk(session_id, chunk_text, **kwargs)
        return self._decision_payload(session_id, decision)

    def on_complete(self, session_id: str, final_text: str = "", **kwargs: Any) -> dict[str, Any]:
        decision = self.rtg.on_complete(session_id, final_text)
        self._remember_reasoning(session_id, decision, final_text)
        return self._decision_payload(session_id, decision)

    def _remember_reasoning(self, session_id: str, decision: Decision, final_text: str) -> None:
        mem = self.memory
        if mem is None:
            return
        neuro = mem if hasattr(mem, "remember_reasoning") else getattr(mem, "neuro", None)
        if neuro is None or not hasattr(neuro, "remember_reasoning"):
            return
        owner = self._agent_by_session.get(session_id, "default")
        try:
            neuro.remember_reasoning(
                f"rtg action={decision.action.value} reason={decision.reason} text={final_text[:400]}",
                owner=owner,
                reasoning_id=session_id,
                metadata={
                    "action": decision.action.value,
                    "reason": decision.reason,
                    "terminal": str(decision.terminal),
                },
                tags=["rtg", "reasoning"],
                confidence=float(getattr(decision, "governor_accuracy_demand", 0.5) or 0.5),
            )
        except Exception:
            pass

    def _decision_payload(self, session_id: str, decision: Decision) -> dict[str, Any]:
        state = self.rtg.controller.get(session_id)
        remaining = state.budget.remaining_tokens if state else 0
        return {
            "session_id": session_id,
            "action": decision.action.value,
            "reason": decision.reason,
            "terminal": decision.terminal,
            "force_close": decision.force_close,
            "thinking_token_cap": remaining,
            "escalate_to_tier": decision.escalate_to_tier,
            "quant_hint": decision.quant_hint,
            "governor_accuracy_demand": decision.governor_accuracy_demand,
            "force_close_message": self.rtg.config.force_close_message
            if decision.force_close
            else "",
            "policy_layer": decision.policy_layer,
        }

    def _frame_from_request(self, request: Any, **kwargs: Any) -> TelemetryFrame:
        session_id = str(
            kwargs.get("session_id")
            or getattr(request, "session_id", "")
            or ""
        )
        messages = list(getattr(request, "messages", []) or [])
        prompt = ""
        if messages:
            last = messages[-1]
            if isinstance(last, dict):
                prompt = str(last.get("content", ""))
            else:
                prompt = str(getattr(last, "content", ""))
        prompt = prompt or str(getattr(request, "prompt_text", "") or "")
        return TelemetryFrame(
            session_id=session_id,
            agent_id=str(getattr(request, "agent_id", "") or ""),
            agent_role=str(getattr(request, "agent_role", "") or ""),
            prompt_text=prompt,
            tool_confidence_top1=float(
                kwargs.get("tool_confidence", getattr(request, "tool_confidence", 0.0)) or 0.0
            ),
            tool_names=list(kwargs.get("tool_names") or getattr(request, "tool_names", []) or []),
            kv_pressure=float(kwargs.get("kv_pressure", 0.0) or 0.0),
            kv_hit_rate=float(kwargs.get("kv_hit_rate", 0.0) or 0.0),
            memory_pressure=float(kwargs.get("memory_pressure", 0.0) or 0.0),
            slo_remaining_ms=float(kwargs.get("slo_remaining_ms", 4000.0) or 4000.0),
            self_consistency_score=float(kwargs.get("self_consistency_score", 0.0) or 0.0),
            cascade_tier=int(kwargs.get("cascade_tier", 1) or 1),
            workflow_type=str(kwargs.get("workflow_type", "chat")),
            agent_priority=float(kwargs.get("agent_priority", 0.5) or 0.5),
        )
