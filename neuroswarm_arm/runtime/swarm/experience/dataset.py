"""Dataset generators — feature rows only, no training."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .execution_record import ExecutionRecord
from .models import DatasetKind


def _base_row(record: ExecutionRecord) -> dict[str, Any]:
    return {
        "execution_id": record.execution_id,
        "workflow_id": record.workflow_id,
        "request_id": record.request_id,
        "session_id": record.session_id,
        "timestamp": record.timestamp.isoformat(),
        "success": record.success,
        "latency": record.latency,
        "queue_latency": record.queue_latency,
        "execution_latency": record.execution_latency,
        "estimated_cost": record.estimated_cost,
        "estimated_energy": record.estimated_energy,
        "quality": record.quality_score.score,
        "retry_count": record.retry_count,
        "models_used": ",".join(record.models_used),
        "backends_used": ",".join(record.backends_used),
        "agents": ",".join(a.agent_id for a in record.agent_assignments),
        "prompt_tokens": record.token_usage.prompt_tokens,
        "completion_tokens": record.token_usage.completion_tokens,
        "reasoning_tokens": record.reasoning_tokens,
        "tags": ",".join(record.tags),
    }


@dataclass
class ExperienceDataset:
    """Tabular dataset derived from execution history."""

    kind: DatasetKind
    rows: list[dict[str, Any]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.rows)

    def to_dicts(self) -> list[dict[str, Any]]:
        return list(self.rows)


class DatasetGenerator:
    """Build benchmark / policy / offline-RL / analytics datasets."""

    def benchmark(self, records: Sequence[ExecutionRecord]) -> ExperienceDataset:
        rows = []
        for r in records:
            row = _base_row(r)
            row.update(
                {
                    "failure_reason": r.failure_reason,
                    "task_graph_reference": r.task_graph_reference,
                    "execution_plan_reference": r.execution_plan_reference,
                    "tool_call_count": len(r.tool_calls),
                    "artifact_count": len(r.artifacts),
                }
            )
            rows.append(row)
        return ExperienceDataset(
            kind=DatasetKind.BENCHMARK,
            rows=rows,
            columns=list(rows[0].keys()) if rows else [],
            metadata={"purpose": "benchmark_evaluation"},
        )

    def policy(self, records: Sequence[ExecutionRecord]) -> ExperienceDataset:
        rows = []
        for r in records:
            row = {
                "execution_id": r.execution_id,
                "workflow_id": r.workflow_id,
                "models_used": list(r.models_used),
                "backends_used": list(r.backends_used),
                "quantizations": list(r.quantizations),
                "agents": [a.agent_id for a in r.agent_assignments],
                "success": r.success,
                "latency": r.latency,
                "cost": r.estimated_cost,
                "quality": r.quality_score.score,
                "budget_max_cost": (
                    r.budget.max_cost_usd if r.budget else None
                ),
                "tags": list(r.tags),
            }
            rows.append(row)
        return ExperienceDataset(
            kind=DatasetKind.POLICY,
            rows=rows,
            columns=list(rows[0].keys()) if rows else [],
            metadata={"purpose": "policy_evolution_features"},
        )

    def offline_rl(self, records: Sequence[ExecutionRecord]) -> ExperienceDataset:
        """Emit (state, action, reward, next_state-ish) feature rows — no training."""
        rows = []
        ordered = sorted(records, key=lambda r: r.timestamp)
        for i, r in enumerate(ordered):
            nxt = ordered[i + 1] if i + 1 < len(ordered) else None
            state = {
                "latency": r.queue_latency,
                "cost_so_far": r.estimated_cost,
                "retry_count": r.retry_count,
                "quality": r.quality_score.score,
            }
            action = {
                "models": list(r.models_used),
                "backends": list(r.backends_used),
                "agents": [a.agent_id for a in r.agent_assignments],
            }
            reward = (1.0 if r.success else -1.0) * max(r.quality_score.score, 0.01)
            reward -= 0.001 * r.latency
            next_state = (
                {
                    "latency": nxt.queue_latency,
                    "cost_so_far": nxt.estimated_cost,
                    "retry_count": nxt.retry_count,
                    "quality": nxt.quality_score.score,
                }
                if nxt is not None
                else {}
            )
            rows.append(
                {
                    "execution_id": r.execution_id,
                    "workflow_id": r.workflow_id,
                    "state": state,
                    "action": action,
                    "reward": reward,
                    "next_state": next_state,
                    "done": nxt is None or r.workflow_id != (nxt.workflow_id if nxt else None),
                }
            )
        return ExperienceDataset(
            kind=DatasetKind.OFFLINE_RL,
            rows=rows,
            columns=list(rows[0].keys()) if rows else [],
            metadata={"purpose": "offline_rl_dataset", "training": False},
        )

    def analytics(self, records: Sequence[ExecutionRecord]) -> ExperienceDataset:
        rows = [_base_row(r) for r in records]
        return ExperienceDataset(
            kind=DatasetKind.ANALYTICS,
            rows=rows,
            columns=list(rows[0].keys()) if rows else [],
            metadata={"purpose": "analytics_export"},
        )

    def generate(
        self,
        kind: DatasetKind | str,
        records: Iterable[ExecutionRecord],
    ) -> ExperienceDataset:
        seq = list(records)
        k = DatasetKind(kind) if isinstance(kind, str) else kind
        if k is DatasetKind.BENCHMARK:
            return self.benchmark(seq)
        if k is DatasetKind.POLICY:
            return self.policy(seq)
        if k is DatasetKind.OFFLINE_RL:
            return self.offline_rl(seq)
        if k is DatasetKind.ANALYTICS:
            return self.analytics(seq)
        raise ValueError(f"unknown dataset kind: {kind}")
