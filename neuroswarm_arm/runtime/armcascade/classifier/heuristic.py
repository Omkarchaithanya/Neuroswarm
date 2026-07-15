"""Heuristic / lightweight request classifier."""

from __future__ import annotations

from typing import TYPE_CHECKING

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import RequestClassifier
from neuroswarm_arm.runtime.armcascade.interfaces.types import Classification, TaskKind

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan, InferenceRequest

_CODE_HINTS = ("```", "def ", "class ", "function", "compile", "bug", "stacktrace", "python", "rust")
_REASON_HINTS = ("reason", "think step", "prove", "why ", "analyze", "chain of thought", "cot")
_JSON_HINTS = ("json", "schema", "{\"", "response_format")
_RAG_HINTS = ("according to", "document", "context:", "retrieve", "citation")
_PLAN_HINTS = ("plan", "roadmap", "steps to", "breakdown", "milestone")
_FACT_HINTS = ("what is", "who is", "when did", "capital of", "define ")


class HeuristicRequestClassifier(RequestClassifier):
    """Classify workload without a heavyweight embedding model.

    Uses prompt heuristics + plan workload + tool signals. Fast, ARM-friendly,
    and good enough to pick speculation strategy defaults.
    """

    def classify(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan | None = None,
    ) -> Classification:
        text = (req.prompt_text or "").lower()
        tools = list(req.tool_names or [])
        streaming = bool(req.stream)
        workload = getattr(getattr(plan, "workload", None), "value", None) or ""

        kind = TaskKind.CHAT
        complexity = 0.4
        entropy = 0.45
        reasoning_depth = 0.1
        expected_latency = float(getattr(req, "latency_sla_ms", 4000.0) or 4000.0) * 0.25
        expected_accept = 0.75
        strategy = "draft_model"
        verify = "block"
        graph = "default_linear"

        if tools or req.tool_schemas or "tool" in workload:
            kind = TaskKind.TOOL_USE
            complexity = 0.55
            entropy = 0.5
            expected_accept = 0.65
            strategy = "draft_model"
            graph = "tool_then_verify"
        if any(h in text for h in _CODE_HINTS) or "coding" in workload:
            kind = TaskKind.CODE
            complexity = 0.7
            entropy = 0.65
            reasoning_depth = 0.4
            expected_accept = 0.55
            strategy = "draft_model"
            verify = "block"
        if any(h in text for h in _REASON_HINTS) or "reasoning" in workload:
            kind = TaskKind.REASONING
            complexity = 0.85
            entropy = 0.8
            reasoning_depth = 0.8
            expected_accept = 0.45
            strategy = "draft_model"
            expected_latency *= 1.5
        if any(h in text for h in _JSON_HINTS):
            kind = TaskKind.JSON
            complexity = 0.5
            entropy = 0.35
            expected_accept = 0.7
            strategy = "ngram"
        if any(h in text for h in _RAG_HINTS):
            kind = TaskKind.RAG
            complexity = 0.6
            entropy = 0.4
            expected_accept = 0.7
            graph = "memory_escalate"
        if any(h in text for h in _PLAN_HINTS):
            kind = TaskKind.PLANNING
            complexity = 0.75
            reasoning_depth = 0.6
            expected_accept = 0.5
        if any(h in text for h in _FACT_HINTS) and kind == TaskKind.CHAT:
            kind = TaskKind.FACTUAL
            complexity = 0.3
            entropy = 0.25
            expected_accept = 0.85
            strategy = "self_speculation"
        if "agent" in text or "multi-agent" in text:
            kind = TaskKind.MULTI_AGENT
            complexity = max(complexity, 0.7)
            graph = "tool_then_verify"
        if streaming:
            if kind == TaskKind.CHAT:
                kind = TaskKind.STREAMING
            expected_latency *= 0.8

        # Repetitive / long prompts favor n-gram self-spec.
        words = text.split()
        if len(words) > 40 and expected_accept > 0.6 and kind in {
            TaskKind.CHAT,
            TaskKind.FACTUAL,
            TaskKind.JSON,
            TaskKind.STREAMING,
        }:
            strategy = "self_speculation"

        return Classification(
            task_kind=kind,
            complexity=complexity,
            entropy_estimate=entropy,
            expected_reasoning_depth=reasoning_depth,
            expected_latency_ms=expected_latency,
            expected_acceptance=expected_accept,
            recommended_strategy=strategy,
            recommended_verify=verify,
            recommended_graph=graph,
            signals={
                "tool_count": float(len(tools)),
                "prompt_tokens_approx": float(max(1, len(words))),
                "streaming": 1.0 if streaming else 0.0,
            },
        )
