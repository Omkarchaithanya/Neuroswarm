"""DI factory for AROP Plane 5."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neuroswarm_arm.evolution.bus.events import EventBus
from neuroswarm_arm.evolution.config import AROPConfig, load_arop_config
from neuroswarm_arm.evolution.deployment.adapters import (
    ASCRDeploymentAdapter,
    AQRDeploymentAdapter,
    HAOEDeploymentAdapter,
    MAKSDeploymentAdapter,
    MemDeploymentAdapter,
    RouterDeploymentAdapter,
    RTGDeploymentAdapter,
)
from neuroswarm_arm.evolution.deployment.engine import DeploymentEngine
from neuroswarm_arm.evolution.deployment.policy_agent import PolicyRegistryBackedAgent
from neuroswarm_arm.evolution.evolution.engine import LineageEvolutionEngine
from neuroswarm_arm.evolution.experiment.engine import ExperimentEngine
from neuroswarm_arm.evolution.knowledge.engine import (
    InMemoryKnowledgeStore,
    KnowledgeEngine,
    Mem0KnowledgeStore,
    OKFKnowledgeStore,
)
from neuroswarm_arm.evolution.observation.aggregator import MetricsAggregator
from neuroswarm_arm.evolution.observation.linux_perf_provider import LinuxPerfProvider, PMUCounterProvider
from neuroswarm_arm.evolution.observation.otel_provider import OpenTelemetryProvider, PrometheusObservationProvider
from neuroswarm_arm.evolution.observation.performix_provider import (
    PerformixMCPObservationProvider,
    PerformixObservationProvider,
)
from neuroswarm_arm.evolution.observation.runtime_provider import RuntimeObservationProvider
from neuroswarm_arm.evolution.optimization.engine import OptimizationEngine
from neuroswarm_arm.evolution.optimization.policy_registry import PolicyRegistry
from neuroswarm_arm.evolution.models.policy import PolicyConstraints
from neuroswarm_arm.evolution.performix_client import PerformixClient
from neuroswarm_arm.evolution.reflection import (
    GEPAReflectionStrategy,
    HybridReflectionStrategy,
    OfflineLLMReflectionStrategy,
    RuleBasedReflectionStrategy,
)
from neuroswarm_arm.evolution.replay.buffer import EpisodeReplayEngine, InMemoryReplayBuffer
from neuroswarm_arm.evolution.rl.experience_store import ExperienceStore, OfflineContextualBandit
from neuroswarm_arm.evolution.runtime_optimizer import RuntimeOptimizer
from neuroswarm_arm.evolution.safety.engine import SafetyEngine
from neuroswarm_arm.evolution.validation.engine import ValidationEngine


@dataclass
class AROPRuntime:
    config: AROPConfig
    optimizer: RuntimeOptimizer
    registry: PolicyRegistry
    aggregator: MetricsAggregator
    runtime_provider: RuntimeObservationProvider
    bus: EventBus
    policy_agent: PolicyRegistryBackedAgent
    gepa: Any | None = None
    approval_gate: Any | None = None
    text_deployer: Any | None = None

    def run_once(self):
        return self.optimizer.run_once()

    def status(self) -> dict[str, Any]:
        st = self.optimizer.status()
        if self.gepa is not None:
            st["gepa"] = {
                "pool": self.gepa.candidate_pool().status(),
                "pareto_n": len(self.gepa.pareto.members()),
                "official_bridge": self.gepa.bridge.available,
            }
        if self.approval_gate is not None:
            st["gepa_pending_approvals"] = len(self.approval_gate.pending())
        return st

    def health(self) -> dict[str, Any]:
        h = self.optimizer.health()
        h["gepa"] = self.gepa is not None
        return h

    def submit_gepa_best(self) -> dict[str, Any]:
        """After GEPA optimize: auto-submit best candidate to ApprovalGate."""
        out: dict[str, Any] = {}
        reflection = getattr(self.optimizer, "reflection", None)
        gepa_strat = getattr(reflection, "gepa", None) if reflection is not None else None
        last = getattr(gepa_strat, "last_result", None) if gepa_strat is not None else None
        if last is None and reflection is not None:
            last = getattr(reflection, "last_result", None)
        best = getattr(last, "best", None) if last is not None else None
        if best is None or self.approval_gate is None:
            return out
        try:
            self.approval_gate.submit(best)
            if self.gepa is not None:
                try:
                    self.gepa.candidate_pool().add(best)
                except Exception:
                    try:
                        self.gepa.candidate_pool().replace_same_id(best)
                    except Exception:
                        pass
            out["gepa_candidate_id"] = best.id
            out["gepa_submitted"] = True
            out["gepa_pending"] = len(self.approval_gate.pending())
        except Exception as exc:
            out["gepa_submit_error"] = str(exc)
        return out


def _build_reflection(name: str, *, gepa_facade: Any | None = None):
    key = (name or "rule").lower()
    if key == "gepa":
        return GEPAReflectionStrategy(facade=gepa_facade)
    if key == "hybrid":
        return HybridReflectionStrategy(gepa_facade=gepa_facade)
    if key in {"offline_llm", "llm"}:
        return OfflineLLMReflectionStrategy()
    return RuleBasedReflectionStrategy()


def build_arop(
    cfg: AROPConfig | None = None,
    *,
    work_dir: Path | None = None,
    okf_root: Path | None = None,
    memory: Any | None = None,
    metrics_bridge: Any | None = None,
    ascr: Any | None = None,
    rtg: Any | None = None,
    router: Any | None = None,
    haoe: Any | None = None,
    maks: Any | None = None,
    aqr: Any | None = None,
    rcis: Any | None = None,
) -> AROPRuntime:
    config = cfg or load_arop_config(work_dir=work_dir, okf_root=okf_root)
    if work_dir is not None:
        config.work_dir = Path(work_dir)
        config.work_dir.mkdir(parents=True, exist_ok=True)
    if okf_root is not None:
        config.okf_root = Path(okf_root)

    bus = EventBus()
    registry = PolicyRegistry(store_path=config.work_dir / "policy_registry.json")

    def _scrape() -> dict[str, float]:
        out: dict[str, float] = {}
        if metrics_bridge is not None and hasattr(metrics_bridge, "snapshot"):
            try:
                snap = metrics_bridge.snapshot()
                if isinstance(snap, dict):
                    for k, v in snap.items():
                        try:
                            out[str(k)] = float(v)
                        except (TypeError, ValueError):
                            continue
            except Exception:
                pass
        return out

    runtime_provider = RuntimeObservationProvider(
        metrics_fn=_scrape,
        haoe_snapshot=config.haoe_snapshot,
    )
    performix = PerformixObservationProvider(
        client=PerformixClient(binary=config.performix_binary),
        output_dir=config.work_dir / "performix",
        recipe=config.performix_recipe,
        enabled=config.performix_enabled,
        snapshot_path=Path("work/performix/snapshot.json"),
    )
    providers = [
        runtime_provider,
        performix,
        PerformixMCPObservationProvider(mcp_url=config.mcp_performix_url, fallback=performix),
        PrometheusObservationProvider(scrape_fn=_scrape),
        OpenTelemetryProvider(),
        LinuxPerfProvider(enabled=False),
        PMUCounterProvider(),
    ]
    if rcis is not None:
        try:
            from neuroswarm_arm.armora.cost.arop_provider import RCISObservationProvider

            providers.append(RCISObservationProvider(rcis))
        except Exception:
            pass
    aggregator = MetricsAggregator(providers)

    mem_store = Mem0KnowledgeStore(memory=memory, fallback=InMemoryKnowledgeStore())
    okf_store = OKFKnowledgeStore(config.okf_root)
    knowledge = KnowledgeEngine(mem_store, okf=okf_store)

    # Official GEPA text subsystem (Plane 5 reflection) — not knob RL
    from neuroswarm_arm.evolution.reflection.gepa import (
        ApprovalGate,
        GEPAFacade,
        TextArtifactDeployer,
    )

    from neuroswarm_arm.evolution.reflection.gepa.mutation.reflective import (
        build_reflection_lm,
    )

    gepa_facade = GEPAFacade(
        work_dir=config.work_dir / "gepa",
        reflection_lm=build_reflection_lm(config.gepa_lm),
    )
    approval_gate = ApprovalGate()
    text_deployer = TextArtifactDeployer(
        artifact_root=config.work_dir / "gepa",
        okf_root=config.okf_root,
        memory=memory,
        pool=gepa_facade.candidate_pool(),
    )

    reflection = _build_reflection(config.reflection_strategy, gepa_facade=gepa_facade)
    constraints = PolicyConstraints(
        max_latency_ms=config.safety_max_latency_ms,
        min_accept_rate=config.safety_min_accept_rate,
        max_cost_usd=config.safety_max_cost_usd,
        max_kv_pressure=config.safety_max_kv_pressure,
    )
    optimization = OptimizationEngine(registry, constraints=constraints)
    replay_engine = EpisodeReplayEngine()
    experience = ExperienceStore(InMemoryReplayBuffer())
    experiment = ExperimentEngine(replay_engine, canary_percent=config.canary_percent)
    validation = ValidationEngine(alpha=config.significance_alpha, min_improvement=config.min_improvement)
    safety = SafetyEngine(config)

    adapters = [
        ASCRDeploymentAdapter(ascr),
        RTGDeploymentAdapter(rtg),
        RouterDeploymentAdapter(router),
        HAOEDeploymentAdapter(haoe),
        MAKSDeploymentAdapter(maks),
        AQRDeploymentAdapter(aqr),
        MemDeploymentAdapter(memory),
    ]
    deployment = DeploymentEngine(registry, adapters=adapters)
    evolution = LineageEvolutionEngine(okf=okf_store)
    bandit = OfflineContextualBandit()

    optimizer = RuntimeOptimizer(
        config,
        aggregator=aggregator,
        knowledge=knowledge,
        reflection=reflection,
        optimization=optimization,
        experiment=experiment,
        validation=validation,
        safety=safety,
        deployment=deployment,
        evolution=evolution,
        registry=registry,
        bus=bus,
        experience=experience,
        bandit=bandit,
    )
    policy_agent = PolicyRegistryBackedAgent(registry)

    return AROPRuntime(
        config=config,
        optimizer=optimizer,
        registry=registry,
        aggregator=aggregator,
        runtime_provider=runtime_provider,
        bus=bus,
        policy_agent=policy_agent,
        gepa=gepa_facade,
        approval_gate=approval_gate,
        text_deployer=text_deployer,
    )
