"""Unit economics accounting over RuntimeCostReport history."""

from __future__ import annotations

from collections import defaultdict

from .schemas import RuntimeCostReport, UnitEconomics, safe_div


class DefaultAccountingEngine:
    def compute(self, reports: list[RuntimeCostReport]) -> UnitEconomics:
        if not reports:
            return UnitEconomics()

        total_cost = sum(r.estimated_dollars for r in reports)
        prompt_toks = sum(r.prompt_tokens for r in reports)
        comp_toks = sum(r.completion_tokens for r in reports)
        reason_toks = sum(r.reasoning_tokens for r in reports)
        useful = sum(r.completion_tokens + r.accepted_speculative_tokens for r in reports)
        accepted = sum(r.accepted_speculative_tokens for r in reports)
        tools = sum(
            int(r.extensions.get("tool_calls", 0)) if isinstance(r.extensions, dict) else 0
            for r in reports
        )
        # Prefer cost_breakdown tool signals when present via estimated dollars share
        tool_cost_sum = sum(r.cost_breakdown.tool_cost for r in reports)
        cpu_s = sum(r.cpu_seconds for r in reports)
        joules = sum(r.energy_estimate_joules for r in reports)

        by_backend: dict[str, list[float]] = defaultdict(list)
        by_quant: dict[str, list[float]] = defaultdict(list)
        by_tier: dict[str, list[float]] = defaultdict(list)
        by_workflow: dict[str, list[float]] = defaultdict(list)
        by_agent: dict[str, list[float]] = defaultdict(list)
        by_conversation: dict[str, list[float]] = defaultdict(list)

        for r in reports:
            if r.backend:
                by_backend[r.backend].append(r.estimated_dollars)
            if r.quantization:
                by_quant[r.quantization].append(r.estimated_dollars)
            if r.model_tier:
                by_tier[r.model_tier].append(r.estimated_dollars)
            if r.workflow_id:
                by_workflow[r.workflow_id].append(r.estimated_dollars)
            if r.agent_id:
                by_agent[r.agent_id].append(r.estimated_dollars)
            conv = r.workflow_id or r.request_id
            by_conversation[conv].append(r.estimated_dollars)

        def _means(groups: dict[str, list[float]]) -> dict[str, float]:
            return {k: safe_div(sum(v), float(len(v))) for k, v in groups.items()}

        n = float(len(reports))
        return UnitEconomics(
            cost_per_prompt_token=safe_div(total_cost, float(prompt_toks)),
            cost_per_completion_token=safe_div(total_cost, float(comp_toks)),
            cost_per_reasoning_token=safe_div(total_cost, float(reason_toks)),
            cost_per_useful_token=safe_div(total_cost, float(useful)),
            cost_per_accepted_draft_token=safe_div(total_cost, float(accepted)),
            cost_per_tool_call=safe_div(tool_cost_sum, float(tools)) if tools else safe_div(tool_cost_sum, 1.0),
            cost_per_cpu_second=safe_div(total_cost, float(cpu_s)),
            cost_per_joule=safe_div(total_cost, float(joules)),
            cost_per_request=safe_div(total_cost, n),
            cost_per_backend=_means(by_backend),
            cost_per_quantization=_means(by_quant),
            cost_per_model_tier=_means(by_tier),
            cost_per_workflow=_means(by_workflow),
            cost_per_agent=_means(by_agent),
            cost_per_conversation={k: sum(v) for k, v in by_conversation.items()},
        )
