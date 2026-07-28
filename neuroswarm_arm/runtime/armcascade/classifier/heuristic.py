"""Heuristic / lightweight request classifier."""

from __future__ import annotations

from typing import TYPE_CHECKING

from neuroswarm_arm.runtime.armcascade.classifier.hardness import HardnessTierMapper
from neuroswarm_arm.runtime.armcascade.interfaces.proposal import RequestClassifier
from neuroswarm_arm.runtime.armcascade.interfaces.types import Classification, TaskKind

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan, InferenceRequest

_hardness_mapper = HardnessTierMapper()

_CODE_HINTS = ("```", "def ", "class ", "function", "compile", "bug", "stacktrace", "python", "rust")
_REASON_HINTS = ("reason", "think step", "step by step", "solve", "prove", "why ", "analyze", "chain of thought", "cot")
_JSON_HINTS = ("json", "schema", "{\"", "response_format")
_RAG_HINTS = ("according to", "document", "context:", "retrieve", "citation")
_PLAN_HINTS = ("plan", "roadmap", "steps to", "breakdown", "milestone")
_EXPLAIN_HINTS = ("explain", "describe", "tell me about", "overview of", "what is", "how does")
_STYLE_ONLY_HINTS = (
    "in an advanced way",
    "advanced way",
    "in depth",
    "in detail",
    "comprehensive",
    "thorough",
)
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

        if tools or req.tool_schemas:
            kind = TaskKind.TOOL_USE
            complexity = 0.55
            entropy = 0.5
            expected_accept = 0.65
            strategy = "draft_model"
            graph = "tool_then_verify"
        if any(h in text for h in _CODE_HINTS) or workload == "coding":
            kind = TaskKind.CODE
            complexity = 0.7
            entropy = 0.65
            reasoning_depth = 0.4
            expected_accept = 0.55
            strategy = "draft_model"
            verify = "block"
        if any(h in text for h in _REASON_HINTS) or workload == "reasoning":
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
        style_only = any(h in text for h in _STYLE_ONLY_HINTS)
        if any(h in text for h in _EXPLAIN_HINTS) and kind == TaskKind.CHAT:
            kind = TaskKind.CHAT
            complexity = 0.38 if style_only else 0.5
            expected_accept = 0.72
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

        hardness = _hardness_classification(req, plan, kind, complexity)
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
            recommended_start_tier=int(hardness.start_tier),
            hardness_band=str(hardness.band.value),
            signals={
                "tool_count": float(len(tools)),
                "prompt_tokens_approx": float(max(1, len(words))),
                "streaming": 1.0 if streaming else 0.0,
            },
        )


def _hardness_classification(
    req: InferenceRequest,
    plan: ExecutionPlan | None,
    kind: TaskKind,
    complexity: float,
):
    partial = Classification(
        task_kind=kind,
        complexity=complexity,
    )
    return _hardness_mapper.classify(req, plan, classification=partial)
