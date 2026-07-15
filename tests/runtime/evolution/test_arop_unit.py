"""AROP unit + pipeline tests (mock providers; no real Performix/GEPA)."""

from __future__ import annotations

from pathlib import Path

from neuroswarm_arm.evolution import build_arop, load_arop_config
from neuroswarm_arm.evolution.bus import AROPEventType, EventBus
from neuroswarm_arm.evolution.deployment.adapters import ASCRDeploymentAdapter
from neuroswarm_arm.evolution.deployment.policy_agent import PolicyRegistryBackedAgent
from neuroswarm_arm.evolution.interfaces.knowledge import KnowledgeView
from neuroswarm_arm.evolution.models.observation import TimeWindow
from neuroswarm_arm.evolution.models.policy import RuntimePolicy
from neuroswarm_arm.evolution.observation.performix_provider import PerformixObservationProvider
from neuroswarm_arm.evolution.optimization.knobs import KNOB_CATALOG, clamp_parameters
from neuroswarm_arm.evolution.optimization.policy_registry import PolicyRegistry
from neuroswarm_arm.evolution.reflection import GEPAReflectionStrategy, RuleBasedReflectionStrategy
from neuroswarm_arm.evolution.rl import ExperienceStore, OfflineContextualBandit
from neuroswarm_arm.evolution.validation.stats import effect_size, welch_t_test
from neuroswarm_arm.runtime.armcascade.interfaces.rl_agent import RLObservation


def test_knob_catalog_covers_layers() -> None:
    layers = {spec.layer.value for spec in KNOB_CATALOG.values()}
    for required in ("haoe", "ascr", "rtg", "router", "maks", "mem", "arop"):
        assert required in layers


def test_clamp_parameters() -> None:
    out = clamp_parameters({"draft_len": 999, "accept_threshold": 1.5})
    assert out["draft_len"] == 64
    assert out["accept_threshold"] == 1.0


def test_policy_registry_canary_sticky() -> None:
    root = Path("work/arop_test_registry")
    root.mkdir(parents=True, exist_ok=True)
    reg = PolicyRegistry(store_path=root / "reg.json")
    base = RuntimePolicy.create(
        policy_id="base",
        version="v0",
        parameters={"draft_len": 8, "accept_threshold": 0.7},
        target_layers={"ascr"},
    )
    canary = RuntimePolicy.create(
        policy_id="canary",
        version="v1",
        parameters={"draft_len": 12, "accept_threshold": 0.8},
        target_layers={"ascr"},
        parent_policy_id="base",
    )
    reg.register(base)
    reg.register(canary)
    reg.set_active("base")
    reg.set_canary("canary", percent=100.0)
    assert reg.resolve(agent_id="any").id == "canary"
    reg.set_canary("canary", percent=0.0)
    assert reg.resolve(agent_id="any").id == "base"


def test_rule_reflection_proposes_on_low_accept() -> None:
    strategy = RuleBasedReflectionStrategy()
    view = KnowledgeView(
        aggregate_metrics={"ascr_accept_rate": 0.4, "ascr_latency_ms": 1000, "draft_len": 8}
    )
    rec = strategy.recommend(view)
    assert rec.deltas
    assert "accept_threshold" in rec.deltas[0].parameters or "draft_len" in rec.deltas[0].parameters


def test_gepa_strategy_emits_no_knob_deltas() -> None:
    """GEPA is text-only — PolicyDelta list must be empty (knobs are RuleBased)."""
    from neuroswarm_arm.evolution.reflection.gepa import GEPAFacade

    facade = GEPAFacade(work_dir=Path("work/arop_test_gepa_strategy"))
    gepa = GEPAReflectionStrategy(facade=facade, max_iterations=1)
    view = KnowledgeView(aggregate_metrics={"ascr_accept_rate": 0.3, "draft_len": 16})
    deltas = gepa.recommend(view).deltas
    assert len(deltas) == 0
    assert gepa.last_result is not None
    assert gepa.last_result.best is not None
    assert "system_prompt" in gepa.last_result.best.components


def test_welch_and_effect() -> None:
    a = [1.0, 1.1, 0.9, 1.05]
    b = [0.5, 0.55, 0.45, 0.5]
    t, p = welch_t_test(a, b)
    assert t != 0
    assert 0 <= p <= 1
    assert effect_size(a, b) > 0


def test_ascr_adapter_to_rl_action() -> None:
    adapter = ASCRDeploymentAdapter(target=object(), dry_run=True)
    applied = adapter.apply({"draft_len": 10, "accept_threshold": 0.8, "verify_batch": 2})
    assert applied["draft_len"] == 10
    action = adapter.to_rl_action()
    assert action.draft_len == 10
    assert action.accept_threshold == 0.8


def test_policy_registry_backed_agent() -> None:
    reg = PolicyRegistry()
    policy = RuntimePolicy.create(
        policy_id="p1",
        version="v1",
        parameters={
            "draft_len": 14,
            "accept_threshold": 0.75,
            "verify_batch": 2,
            "escalate_threshold": 0.35,
            "speculation_depth": 2,
        },
        target_layers={"ascr"},
    )
    reg.register(policy)
    reg.set_active("p1")
    agent = PolicyRegistryBackedAgent(reg)
    action = agent.act(RLObservation())
    assert action.draft_len == 14
    assert action.accept_threshold == 0.75


def test_bandit_cold_start_and_fit() -> None:
    bandit = OfflineContextualBandit()
    deltas = bandit.propose({"ascr_accept_rate": 0.4})
    assert deltas
    store = ExperienceStore()
    store.add({"a": 1.0}, {"draft_len": 6}, 0.8, {"a": 1.1})
    store.add({"a": 1.0}, {"draft_len": 6}, 0.7, {"a": 1.0})
    bandit.fit(store.buffer.all())
    assert bandit.propose({"a": 1.0})


def test_event_bus() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(AROPEventType.PIPELINE_COMPLETE, lambda e: seen.append(e.type.value))
    bus.emit(AROPEventType.PIPELINE_COMPLETE, ok=True)
    assert seen == ["pipeline_complete"]


def test_build_arop_pipeline_end_to_end() -> None:
    root = Path("work/arop_test_pipeline")
    root.mkdir(parents=True, exist_ok=True)
    cfg = load_arop_config(work_dir=root / "arop", okf_root=root / "okf")
    cfg.performix_enabled = False
    cfg.auto_promote = True
    cfg.min_improvement = 0.0
    cfg.significance_alpha = 1.0
    (root / "okf").mkdir(parents=True, exist_ok=True)

    runtime = build_arop(cfg)
    runtime.runtime_provider.record(
        {
            "ascr_accept_rate": 0.4,
            "ascr_latency_ms": 3500.0,
            "kv_pressure": 0.85,
            "cpu_util": 0.9,
            "draft_len": 12,
            "reasoning_cap": 512,
            "router_top_k": 3,
            "reward_scalar": 0.1,
        }
    )
    result = runtime.run_once()
    assert result.status in {"canary", "promoted", "rejected", "rolled_back", "noop"}
    assert runtime.health()["healthy"] is True
    result2 = runtime.run_once()
    assert result2.status in {"canary", "promoted", "rejected", "rolled_back", "noop"}


def test_immutable_policy_hash() -> None:
    p1 = RuntimePolicy.create(
        policy_id="a",
        version="v1",
        parameters={"draft_len": 8},
        target_layers={"ascr"},
    )
    p2 = RuntimePolicy.create(
        policy_id="b",
        version="v1",
        parameters={"draft_len": 8},
        target_layers={"ascr"},
    )
    assert p1.content_hash == p2.content_hash
    p3 = RuntimePolicy.create(
        policy_id="c",
        version="v1",
        parameters={"draft_len": 9},
        target_layers={"ascr"},
    )
    assert p3.content_hash != p1.content_hash


def test_performix_provider_disabled() -> None:
    p = PerformixObservationProvider(enabled=False)
    events = p.collect(TimeWindow.last_seconds(10))
    assert events
    assert p.health().healthy
