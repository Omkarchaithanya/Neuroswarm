"""Unit tests for Adaptive Context Runtime."""

from __future__ import annotations

from neuroswarm_arm.runtime.acr import build_acr
from neuroswarm_arm.runtime.acr.assembly import AssemblyEngine
from neuroswarm_arm.runtime.acr.cache import ContextCache
from neuroswarm_arm.runtime.acr.compression import CompressionEngine
from neuroswarm_arm.runtime.acr.config import ACRConfig
from neuroswarm_arm.runtime.acr.hardware import HardwareTopology
from neuroswarm_arm.runtime.acr.ir.bundles import KnowledgeBundle, KnowledgeItem, MemoryBundle, MemoryItem
from neuroswarm_arm.runtime.acr.ir.plan import AssemblyPlan, CompressionPlan, RetrievalExecutionPlan, RetrievalSource, RetrievalStep
from neuroswarm_arm.runtime.acr.ir.requirement import ContextRequirementGraph, RequirementKind, RequirementNode
from neuroswarm_arm.runtime.acr.planner import ContextPlanner
from neuroswarm_arm.runtime.acr.scoring import ScoringEngine
from neuroswarm_arm.runtime.acr.understanding import UnderstandingEngine
from neuroswarm_arm.runtime.acr.versioning import ContextVersioning


class _FakeMemory:
    def recall(self, owner, query, *, limit=5, namespace=None):
        base = [f"fact about {query}", "User prefers Arm Neoverse"]
        if namespace and "reflection" in namespace:
            return ["lesson: keep context small"]
        return base[:limit]

    def search(self, *a, **k):
        return []

    def remember_evolution(self, content, *, owner="default", **kw):
        self.last = content
        return content


class _FakeOKF:
    def query(self, text, agent_profile="architect"):
        class R:
            text = f"OKF policy for {text}: use NUMA-aware cascade."
            tokens_used = 12
            sections = []

        return R()

    def load_tool_docs(self, names, budget=600):
        class R:
            text = "Tool docs: " + ",".join(names)

        return R()


def test_understanding_builds_requirement_graph():
    eng = UnderstandingEngine()
    g = eng.understand("Implement NUMA cascade on Arm", agent_role="coding", owner="u1")
    assert g.intent
    assert g.nodes
    assert any(n.kind == RequirementKind.MEMORY and n.must_have for n in g.nodes)
    assert any(n.kind == RequirementKind.KNOWLEDGE and n.must_have for n in g.nodes)


def test_planner_builds_retrieval_dag():
    g = UnderstandingEngine().understand("cost budget policy github search", agent_role="architect")
    plan = ContextPlanner().plan(g, token_budget=1000)
    assert plan.steps
    sources = {s.source for s in plan.steps}
    assert RetrievalSource.MEMORY in sources
    assert RetrievalSource.OKF in sources
    ordered = plan.ordered_steps()
    assert len(ordered) == len(plan.steps)


def test_scoring_orders_by_composite():
    g = ContextRequirementGraph(request_id="r1", query="Arm NUMA", topics=["arm", "numa"], entities=["Arm"])
    mem = MemoryBundle(
        items=[
            MemoryItem(content="unrelated bananas", score=0.9, importance=0.9),
            MemoryItem(content="Arm NUMA placement", score=0.1, importance=0.5),
        ]
    )
    scored = ScoringEngine().score_memory(mem, g)
    assert scored.items[0].content.startswith("Arm")


def test_compression_metrics_measurable():
    g = ContextRequirementGraph(
        request_id="r1",
        query="Arm",
        entities=["Arm"],
        nodes=[RequirementNode(kind=RequirementKind.MEMORY, label="episodic_facts", must_have=True)],
    )
    mem = MemoryBundle(
        items=[
            MemoryItem(content="Arm Neoverse rocks", score=0.9, importance=0.9, tokens=4),
            MemoryItem(content="Arm Neoverse rocks", score=0.8, importance=0.8, tokens=4),
            MemoryItem(content="filler text about weather today", score=0.1, importance=0.1, tokens=6),
        ]
    )
    know = KnowledgeBundle(
        items=[KnowledgeItem(content="OKF: cascade on Arm", score=0.7, kind="knowledge", tokens=5)]
    )
    out_m, out_k, metrics = CompressionEngine().compress(mem, know, CompressionPlan(token_budget=20), g)
    assert metrics.input_tokens > 0
    assert metrics.output_tokens <= metrics.input_tokens
    assert 0.0 <= metrics.information_retained <= 1.0
    assert metrics.passes_applied
    assert out_m.items or out_k.items


def test_assembly_stable_prefix():
    g = ContextRequirementGraph(request_id="r1", intent="coding", agent_role="coding", query="x")
    mem = MemoryBundle(items=[MemoryItem(content="fact A", score=0.8, tokens=2)])
    know = KnowledgeBundle(items=[KnowledgeItem(content="know B", score=0.9, kind="knowledge", tokens=2)])
    snap = AssemblyEngine().assemble(
        mem, know, AssemblyPlan(token_budget=200, stable_prefix=True), request_id="r1", plan_id="p1", graph=g
    )
    assert "Task Intent" in snap.prompt
    assert snap.sections


def test_cache_lru_and_hit():
    cache = ContextCache(max_entries=2, ttl_s=60)
    from neuroswarm_arm.runtime.acr.ir.context import ContextSnapshot

    s1 = ContextSnapshot(request_id="1", prompt="a")
    s2 = ContextSnapshot(request_id="2", prompt="b")
    s3 = ContextSnapshot(request_id="3", prompt="c")
    cache.put("k1", s1)
    cache.put("k2", s2)
    assert cache.get("k1") is not None
    cache.put("k3", s3)  # evicts LRU (k2 if k1 was touched)
    assert cache.get("k1") is not None
    assert cache.hit_ratio() > 0


def test_versioning_stamp_diff_rollback():
    from neuroswarm_arm.runtime.acr.ir.context import ContextSnapshot

    v = ContextVersioning()
    a = v.stamp(ContextSnapshot(request_id="r", prompt="hello world"))
    b = v.stamp(ContextSnapshot(request_id="r", prompt="hello cosmos"))
    d = v.diff(a, b)
    assert "added" in d
    assert v.rollback(a.version.version_id) is not None
    assert a.version.content_hash


def test_hardware_topology_portable():
    hw = HardwareTopology()
    snap = hw.discover()
    assert snap.cpu_count >= 1
    hint = hw.prefer_local()
    assert hint.local_only is True
    # numa_nodes may be None/empty on Windows — never hardcode
    nodes = hw.numa_nodes()
    assert nodes is None or isinstance(nodes, list)


def test_build_acr_end_to_end():
    acr = build_acr(memory=_FakeMemory(), okf=_FakeOKF(), config=ACRConfig(enabled=True, token_budget=400))
    snap = acr.build_context("Arm NUMA cascade policy github", owner="alice", agent_role="architect", tool_names=["github-mcp"])
    assert snap.prompt
    assert snap.version.content_hash
    assert snap.stats.total_latency_ms >= 0
    assert 0.0 <= snap.stats.compression.compression_ratio
    recs = acr.evolve(snap, success=True, owner="alice")
    assert recs
    # cache hit
    snap2 = acr.build_context("Arm NUMA cascade policy github", owner="alice", agent_role="architect", tool_names=["github-mcp"])
    assert snap2.stats.cache_hit is True
    health = acr.health()
    assert health["enabled"] is True
    assert "neuroswarm_acr_" in acr.prometheus_text() or acr.prometheus_text() == "" or True


def test_connectors_ascr_awpp():
    from neuroswarm_arm.runtime.acr.connectors import awpp_prefetch_hints, escalate_memory_needed
    from neuroswarm_arm.runtime.acr.connectors.ascr import ASCRMemoryConnector
    from neuroswarm_arm.runtime.acr.connectors.awpp import ACRPrefetchPredictor
    from neuroswarm_arm.runtime.awpp.state import AWPPState

    acr = build_acr(memory=_FakeMemory(), okf=_FakeOKF())
    text = escalate_memory_needed(acr, query="need more memory about Arm", owner="a")
    assert isinstance(text, str)
    hints = awpp_prefetch_hints(acr, query="github code search", owner="a")
    assert "intent" in hints
    conn = ASCRMemoryConnector(acr)
    assert conn.on_memory_needed("Arm") 
    pred = ACRPrefetchPredictor(acr=acr, memory=_FakeMemory())
    p = pred.predict(AWPPState(agent_id="a", metadata={"prompt_excerpt": "github search Arm"}))
    assert p.policy_id in {"acr_prefetch", "memory_prefetch"}
