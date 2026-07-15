"""Shared fixtures for Experience Store tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.experience import (
    AgentAssignment,
    ArtifactKind,
    ArtifactRef,
    BudgetSnapshot,
    ExecutionRecord,
    QualityScore,
    TokenUsage,
    ToolCallRef,
    build_experience_store,
)


def make_record(**overrides) -> ExecutionRecord:
    base = dict(
        workflow_id="wf_test",
        request_id="req_1",
        session_id="sess_1",
        latency=100.0,
        queue_latency=10.0,
        execution_latency=90.0,
        estimated_cost=0.05,
        estimated_energy=1.2,
        success=True,
        models_used=["llama-3.1-8b"],
        backends_used=["llamacpp"],
        quantizations=["q4_k_m"],
        agent_assignments=[
            AgentAssignment(agent_id="agt_coder", agent_type="coding")
        ],
        tool_calls=[ToolCallRef(tool_name="web_search", latency_ms=5.0)],
        token_usage=TokenUsage(
            prompt_tokens=100, completion_tokens=50, total_tokens=150
        ),
        quality_score=QualityScore(
            execution=0.9,
            tool_correctness=0.8,
            workflow_completion=1.0,
            latency_objective=0.7,
            budget_objective=0.85,
        ),
        budget=BudgetSnapshot(envelope_id="env_1", max_cost_usd=1.0),
        artifacts=[
            ArtifactRef(
                artifact_id="art_1",
                kind=ArtifactKind.OUTPUT,
                uri="file:///tmp/out.txt",
            )
        ],
        tags=["chat", "axion"],
        metrics={"tokens_per_sec": 40.0},
    )
    base.update(overrides)
    return ExecutionRecord(**base)


def fresh_store(**kwargs):
    return build_experience_store(**kwargs)
