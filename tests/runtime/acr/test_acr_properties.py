"""Property-style tests for ACR IR invariants."""

from __future__ import annotations

from neuroswarm_arm.runtime.acr.ir.plan import RetrievalExecutionPlan, RetrievalSource, RetrievalStep
from neuroswarm_arm.runtime.acr.ir.stats import CompressionMetrics


def test_retrieval_plan_order_respects_deps():
    a = RetrievalStep(id="a", source=RetrievalSource.REFLECTION, priority=0.5)
    b = RetrievalStep(id="b", source=RetrievalSource.MEMORY, priority=0.9, depends_on=["a"])
    c = RetrievalStep(id="c", source=RetrievalSource.OKF, priority=0.95, depends_on=["b"])
    plan = RetrievalExecutionPlan(steps=[c, b, a])
    ordered = [s.id for s in plan.ordered_steps()]
    assert ordered.index("a") < ordered.index("b") < ordered.index("c")


def test_compression_metrics_finalize():
    m = CompressionMetrics(input_tokens=100, output_tokens=40)
    m.finalize()
    assert abs(m.compression_ratio - 0.4) < 1e-9
    assert abs(m.token_reduction - 0.6) < 1e-9
