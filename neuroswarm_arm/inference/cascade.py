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

    def _confidence(self, text: str) -> float:
        if not text.strip():
            return 0.0
        score = 0.5
        score += min(0.4, len(text) / 8000.0)
        if "I don't know" in text or "cannot" in text.lower():
            score -= 0.2
        return max(0.0, min(1.0, score))

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

    def _extract_text(self, payload: dict) -> str:
        try:
            return payload["choices"][0]["message"]["content"]
        except Exception:
            return str(payload)

