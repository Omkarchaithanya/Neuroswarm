<<<<<<< HEAD
"""Cascade facade — delegates to DIPA CascadeEngine / DIPARuntime.

Prefer ``neuroswarm_arm.runtime.dipa.build_dipa`` for new code. This module
keeps the historical ``CascadeRouter.handle`` API used by gateway / tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..aqr import pick_quant
from ..governor import ReasoningGovernor
from ..schemas import ChatRequest, ChatResponse
from .llama_client import LlamaClient

if TYPE_CHECKING:
    from ..runtime.dipa import DIPARuntime
    from ..runtime.kv.manager.runtime import KVRuntimeManager


@dataclass
class CascadeRouter:
    """Compat wrapper: prefers injected DIPARuntime; else legacy tier clients."""

    tier1: LlamaClient | None = None
    tier2: LlamaClient | None = None
    tier3: LlamaClient | None = None
    governor: ReasoningGovernor = field(default_factory=ReasoningGovernor)
    confidence_threshold: float = 0.85
    kv_runtime: KVRuntimeManager | None = None
    dipa: DIPARuntime | None = None

    def handle(self, req: ChatRequest, tool_names: list[str] | None = None, **kwargs: Any) -> ChatResponse:
        names = list(tool_names or [])
        if self.dipa is not None:
            return self._handle_via_dipa(req, names, **kwargs)
        return self._handle_legacy(req, names)

    def _handle_via_dipa(
        self, req: ChatRequest, tool_names: list[str], **kwargs: Any
    ) -> ChatResponse:
        from ..schemas import PlanState

        prompt_text = req.messages[-1].content if req.messages else ""
        kv_fields = self._kv_plan_fields(req)
        confidence = float(kwargs.get("tool_confidence") or (0.9 if tool_names else 0.4))
        plan = PlanState(
            tool_confidence_top1=confidence,
            slo_remaining_ms=4000.0,
            self_consistency_score=min(1.0, len(prompt_text.split()) / 256.0),
            session_id=req.session_id or "",
            **kv_fields,
        )
        cap = self.governor.cap(plan)
        system = self.governor.prompt(plan)
        # Mutate a copy so DIPA sees governor system prompt + token cap.
        payload = req.model_copy(
            update={
                "max_tokens": min(req.max_tokens, cap),
            }
        )
        assert self.dipa is not None
        # Attach system prompt via normalize path on ChatRequest-like object
        # by temporarily stuffing into a thin adapter.
        adapter = _GovernorRequest(payload, system, cap, tool_names)
        return self.dipa.handle(
            adapter,
            tool_names,
            tool_schemas=kwargs.get("tool_schemas"),
            tool_confidence=confidence,
            tool_prompt_block=kwargs.get("tool_prompt_block"),
        )

    def _handle_legacy(self, req: ChatRequest, tool_names: list[str]) -> ChatResponse:
        # Preserved path for unit tests that construct CascadeRouter with clients only.
        from ..metrics import metrics
        from ..schemas import ChatChoice, ChatUsage, Message, PlanState
        import time

        if self.tier1 is None or self.tier2 is None or self.tier3 is None:
            raise RuntimeError("CascadeRouter requires dipa or tier LlamaClients")

        prompt_text = req.messages[-1].content if req.messages else ""
        kv_fields = self._kv_plan_fields(req)
        plan = PlanState(
            tool_confidence_top1=0.9 if tool_names else 0.4,
            slo_remaining_ms=4000.0,
            self_consistency_score=min(1.0, len(prompt_text.split()) / 256.0),
            session_id=req.session_id or "",
            **kv_fields,
        )
        cap = self.governor.cap(plan)
        quant = pick_quant(req.agent_role, prompt_text)
        messages = [m.model_dump() for m in req.messages]
        messages = [{"role": "system", "content": self.governor.prompt(plan)}] + messages

        start = time.monotonic()
        tier1 = self.tier1.chat(
            messages, max_tokens=min(req.max_tokens, cap), temperature=req.temperature
        )
        tier1_text = self._extract_text(tier1)
        conf = self._confidence(tier1_text)
        tier_used = 1
        content = tier1_text

        if conf < self.confidence_threshold:
            tier_used = 2
            tier2 = self.tier2.chat(
                messages, max_tokens=req.max_tokens, temperature=req.temperature
            )
            content = self._extract_text(tier2)
            conf = self._confidence(content)
            if conf < 0.5:
                tier_used = 3
                tier3 = self.tier3.chat(
                    messages, max_tokens=req.max_tokens, temperature=req.temperature
                )
                content = self._extract_text(tier3)

        elapsed_ms = (time.monotonic() - start) * 1000.0
        prompt_tokens = self._approx_tokens(prompt_text)
        completion_tokens = self._approx_tokens(content)
        metrics.inc("neuroswarm_requests_total")
        metrics.set("neuroswarm_last_request_latency_ms", elapsed_ms)
        metrics.set("neuroswarm_last_tier_used", float(tier_used))
        metrics.inc(f"neuroswarm_cascade_tier_{tier_used}_total")
        metrics.set("neuroswarm_last_thinking_token_cap", float(cap))
        metrics.set("neuroswarm_last_tool_schema_count", float(len(tool_names)))

        return ChatResponse(
            model=req.model,
            tier_used=tier_used,
            content=content,
            choices=[ChatChoice(message=Message(role="assistant", content=content))],
            usage=ChatUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            tool_schemas_used=tool_names,
            thinking_token_cap=cap,
            metrics={
                "latency_ms": elapsed_ms,
                "tool_schema_count": float(len(tool_names)),
                "quant_policy": quant,
                "tier_used": float(tier_used),
                "prompt_tokens": float(prompt_tokens),
                "completion_tokens": float(completion_tokens),
                "kv_pressure": float(plan.kv_pressure),
                "kv_hit_rate": float(plan.kv_hit_rate),
                "kv_storage_tier": float(plan.kv_storage_tier),
            },
        )

    def _kv_plan_fields(self, req: ChatRequest) -> dict:
        if self.kv_runtime is None:
            return {
                "kv_pressure": min(1.0, max(0.0, req.max_tokens / 16384.0)),
                "kv_hit_rate": 0.0,
                "kv_storage_tier": 1,
                "kv_migration_latency_ms": 0.0,
                "memory_pressure": min(1.0, max(0.0, req.max_tokens / 16384.0)),
            }
        snap = self.kv_runtime.pressure_snapshot()
        return {
            "kv_pressure": snap.pressure,
            "kv_hit_rate": snap.hit_rate,
            "kv_storage_tier": int(snap.dominant_tier),
            "kv_migration_latency_ms": snap.migration_latency_ms,
            "memory_pressure": snap.pressure,
        }
=======
from __future__ import annotations

from dataclasses import dataclass, field
import time

from ..aqr import pick_quant
from ..governor import ReasoningGovernor
from ..metrics import metrics
from ..schemas import ChatRequest, ChatResponse, PlanState
from .llama_client import LlamaClient


@dataclass
class CascadeRouter:
    tier1: LlamaClient
    tier2: LlamaClient
    tier3: LlamaClient
    governor: ReasoningGovernor = field(default_factory=ReasoningGovernor)
    confidence_threshold: float = 0.85
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84

    def _confidence(self, text: str) -> float:
        if not text.strip():
            return 0.0
        score = 0.5
        score += min(0.4, len(text) / 8000.0)
        if "I don't know" in text or "cannot" in text.lower():
            score -= 0.2
        return max(0.0, min(1.0, score))

<<<<<<< HEAD
=======
    def handle(self, req: ChatRequest, tool_names: list[str]) -> ChatResponse:
        plan = PlanState(
            tool_confidence_top1=0.9 if tool_names else 0.4,
            kv_pressure=0.2,
            slo_remaining_ms=4000.0,
            self_consistency_score=0.0,
        )
        cap = self.governor.cap(plan)
        quant = pick_quant(req.agent_role, req.agent_role)
        messages = [m.model_dump() for m in req.messages]
        messages = [{"role": "system", "content": self.governor.prompt(plan)}] + messages

        start = time.time()
        tier1 = self.tier1.chat(messages, max_tokens=min(req.max_tokens, cap), temperature=req.temperature)
        tier1_text = self._extract_text(tier1)
        conf = self._confidence(tier1_text)
        tier_used = 1
        content = tier1_text

        if conf < self.confidence_threshold:
            tier_used = 2
            tier2 = self.tier2.chat(messages, max_tokens=req.max_tokens, temperature=req.temperature)
            content = self._extract_text(tier2)
            conf = self._confidence(content)
            if conf < 0.5:
                tier_used = 3
                tier3 = self.tier3.chat(messages, max_tokens=req.max_tokens, temperature=req.temperature)
                content = self._extract_text(tier3)

        elapsed_ms = (time.time() - start) * 1000.0
        metrics.inc("neuroswarm_requests_total")
        metrics.set("neuroswarm_last_request_latency_ms", elapsed_ms)
        metrics.set("neuroswarm_last_tier_used", float(tier_used))

        return ChatResponse(
            model=req.model,
            tier_used=tier_used,
            content=content,
            tool_schemas_used=tool_names,
            thinking_token_cap=cap,
            metrics={"latency_ms": elapsed_ms, "quant": float(len(quant))},
        )

>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
    def _extract_text(self, payload: dict) -> str:
        try:
            return payload["choices"][0]["message"]["content"]
        except Exception:
            return str(payload)

<<<<<<< HEAD
    def _approx_tokens(self, text: str) -> int:
        if not text.strip():
            return 0
        return max(1, len(text.split()))


@dataclass
class _GovernorRequest:
    """Thin adapter so DIPA RequestRouter sees system_prompt + thinking cap."""

    req: ChatRequest
    system_prompt: str
    thinking_token_cap: int
    tool_names: list[str]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.req, name)
=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
