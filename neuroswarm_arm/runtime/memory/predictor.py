"""Speculative next-action prediction from memory patterns."""

from __future__ import annotations

from collections import Counter

from neuroswarm_arm.runtime.memory.schemas import MemoryRecord, MemoryType, PredictionResult


class Predictor:
    def predict(self, records: list[MemoryRecord], *, context: str = "") -> PredictionResult:
        tools = Counter()
        workflows = Counter()
        models = Counter()
        for rec in records:
            if rec.type == MemoryType.TOOL:
                tid = rec.metadata.get("tool_id") or ""
                if tid:
                    tools[str(tid)] += 1 + int(rec.success_score > 0.5)
            if rec.type == MemoryType.WORKFLOW and rec.workflow_id:
                workflows[rec.workflow_id] += 1
            model = rec.metadata.get("model") or rec.metadata.get("next_model")
            if model:
                models[str(model)] += 1
            # parse tool success lines from history ranker
            if "success tool=" in rec.content:
                part = rec.content.split("success tool=", 1)[-1].split()[0]
                tools[part] += 2
        next_tool = tools.most_common(1)[0][0] if tools else ""
        next_workflow = workflows.most_common(1)[0][0] if workflows else "chat"
        next_model = models.most_common(1)[0][0] if models else ""
        conf = 0.0
        if tools or workflows:
            conf = min(0.95, 0.3 + 0.1 * (len(tools) + len(workflows)))
        return PredictionResult(
            next_workflow=next_workflow,
            next_tool=next_tool,
            next_model=next_model,
            next_planner="workflow_planner",
            next_memory="reflection/" if "fail" in context.lower() else "agents/",
            next_retrieval=context or "context",
            confidence=conf,
            scores={"tools": float(sum(tools.values())), "workflows": float(sum(workflows.values()))},
        )
