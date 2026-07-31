"""Deployment adapters — apply RuntimePolicy knobs to layer runtimes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class AdapterState:
    applied: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False


class DeploymentAdapter(ABC):
    layer: str = "base"

    def __init__(self, target: Any | None = None, *, dry_run: bool = False) -> None:
        self.target = target
        self.state = AdapterState(dry_run=dry_run)

    @abstractmethod
    def apply(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def supported_keys(self) -> set[str]:
        return set()


class ASCRDeploymentAdapter(DeploymentAdapter):
    layer = "ascr"
    KEYS = {
        "accept_threshold",
        "escalate_threshold",
        "draft_len",
        "verify_batch",
        "speculation_depth",
        "draft_model",
        "verify_strategy",
        "self_speculation",
    }

    def supported_keys(self) -> set[str]:
        return set(self.KEYS)

    def apply(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        applied = {k: parameters[k] for k in self.KEYS if k in parameters}
        self.state.applied.update(applied)
        if self.target is not None and not self.state.dry_run:
            # Prefer RLAction-shaped update if available
            try:
                from neuroswarm_arm.runtime.armcascade.interfaces.rl_agent import RLAction

                action = RLAction(
                    draft_len=int(applied.get("draft_len", 8)),
                    accept_threshold=float(applied.get("accept_threshold", 0.7)),
                    verify_batch_size=int(applied.get("verify_batch", 1)),
                    escalate_threshold=float(applied.get("escalate_threshold", 0.4)),
                    speculation_depth=int(applied.get("speculation_depth", 1)),
                )
                if hasattr(self.target, "apply_rl_action"):
                    self.target.apply_rl_action(action)
                elif hasattr(self.target, "set_policy_action"):
                    self.target.set_policy_action(action)
                else:
                    # Store on target for PolicyRegistryBackedAgent consumers
                    setattr(self.target, "_arop_rl_action", action)
            except Exception:
                setattr(self.target, "_arop_params", dict(applied))
        return applied

    def to_rl_action(self, parameters: Mapping[str, Any] | None = None):
        from neuroswarm_arm.runtime.armcascade.interfaces.rl_agent import RLAction

        p = parameters or self.state.applied
        return RLAction(
            draft_len=int(p.get("draft_len", 8)),
            accept_threshold=float(p.get("accept_threshold", 0.7)),
            verify_batch_size=int(p.get("verify_batch", 1)),
            escalate_threshold=float(p.get("escalate_threshold", 0.4)),
            speculation_depth=int(p.get("speculation_depth", 1)),
        )


class RTGDeploymentAdapter(DeploymentAdapter):
    layer = "rtg"
    KEYS = {"reasoning_cap", "budget_usd"}

    def supported_keys(self) -> set[str]:
        return set(self.KEYS)

    def apply(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        applied = {k: parameters[k] for k in self.KEYS if k in parameters}
        self.state.applied.update(applied)
        if self.target is not None and not self.state.dry_run:
            if "reasoning_cap" in applied and hasattr(self.target, "set_token_budget"):
                try:
                    self.target.set_token_budget(int(applied["reasoning_cap"]))
                except Exception:
                    setattr(self.target, "_arop_reasoning_cap", int(applied["reasoning_cap"]))
            else:
                setattr(self.target, "_arop_params", {**getattr(self.target, "_arop_params", {}), **applied})
        return applied


class RouterDeploymentAdapter(DeploymentAdapter):
    layer = "router"
    KEYS = {"router_top_k", "mcp_routing_threshold", "model_routing", "planning_depth", "agent_topology"}

    def supported_keys(self) -> set[str]:
        return set(self.KEYS)

    def apply(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        applied = {k: parameters[k] for k in self.KEYS if k in parameters}
        self.state.applied.update(applied)
        if self.target is not None and not self.state.dry_run:
            if "router_top_k" in applied:
                if hasattr(self.target, "top_k"):
                    try:
                        self.target.top_k = int(applied["router_top_k"])
                    except Exception:
                        pass
                cfg = getattr(self.target, "config", None)
                if cfg is not None and hasattr(cfg, "top_k"):
                    try:
                        cfg.top_k = int(applied["router_top_k"])
                    except Exception:
                        pass
            setattr(self.target, "_arop_params", {**getattr(self.target, "_arop_params", {}), **applied})
        return applied


class AQRDeploymentAdapter(DeploymentAdapter):
    layer = "aqr"
    KEYS = {"quant_preference", "cascade_tier_bias"}

    def supported_keys(self) -> set[str]:
        return set(self.KEYS)

    def apply(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        applied = {k: parameters[k] for k in self.KEYS if k in parameters}
        self.state.applied.update(applied)
        if self.target is not None and not self.state.dry_run:
            if "quant_preference" in applied and hasattr(self.target, "set_arop_quant_preference"):
                try:
                    self.target.set_arop_quant_preference(str(applied["quant_preference"]))
                except Exception:
                    pass
            if "cascade_tier_bias" in applied:
                try:
                    from neuroswarm_arm.runtime.router.cost_router import CostRouter

                    CostRouter.set_arop_tier_floor(int(applied["cascade_tier_bias"]))
                except Exception:
                    pass
            setattr(self.target, "_arop_params", {**getattr(self.target, "_arop_params", {}), **applied})
        return applied


class MAKSDeploymentAdapter(DeploymentAdapter):
    layer = "maks"
    KEYS = {"maks_eviction_weight", "maks_prefetch", "maks_tier_threshold"}

    def supported_keys(self) -> set[str]:
        return set(self.KEYS)

    def apply(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        applied = {k: parameters[k] for k in self.KEYS if k in parameters}
        self.state.applied.update(applied)
        if self.target is not None and not self.state.dry_run:
            # Live knobs — exit dry-run stubs
            thr = applied.get("maks_tier_threshold")
            if thr is not None and hasattr(self.target, "config"):
                try:
                    self.target.config.pressure_threshold = float(thr)
                    if hasattr(self.target, "pressure_monitor"):
                        self.target.pressure_monitor.threshold = float(thr)
                except Exception:
                    pass
            weight = applied.get("maks_eviction_weight")
            if weight is not None and hasattr(self.target, "eviction"):
                try:
                    from neuroswarm_arm.runtime.maks.policies.scored import (
                        EvictionWeights,
                        ScoredEvictionPolicy,
                    )

                    policy = getattr(self.target.eviction, "policy", None)
                    if isinstance(policy, ScoredEvictionPolicy):
                        w = float(weight)
                        policy.weights = EvictionWeights(
                            recency=w,
                            frequency=w,
                            sharing=max(w, 1.0),
                            importance=w,
                        )
                except Exception:
                    pass
            if "maks_prefetch" in applied and hasattr(self.target, "prefetch_engine"):
                try:
                    setattr(
                        self.target.prefetch_engine,
                        "enabled",
                        bool(applied["maks_prefetch"]),
                    )
                except Exception:
                    pass
            setattr(self.target, "_arop_params", {**getattr(self.target, "_arop_params", {}), **applied})
        return applied


class HAOEDeploymentAdapter(DeploymentAdapter):
    layer = "haoe"
    KEYS = {
        "thread_count",
        "openmp_schedule",
        "numa_placement",
        "kv_layout",
        "sglang_batch",
        "llamacpp_ctx",
        "prefill_decode_split",
        "speculative_mode",
    }

    def supported_keys(self) -> set[str]:
        return set(self.KEYS)

    def apply(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        applied = {k: parameters[k] for k in self.KEYS if k in parameters}
        self.state.applied.update(applied)
        if self.target is not None and not self.state.dry_run:
            setattr(self.target, "_arop_params", {**getattr(self.target, "_arop_params", {}), **applied})
        return applied


class MemDeploymentAdapter(DeploymentAdapter):
    layer = "mem"
    KEYS = {
        "mem0_retention",
        "retrieval_depth",
        "context_budget",
        "context_summarization",
        "semantic_cache",
        "memory_eviction",
        "replay_policy",
        "okf_compression",
    }

    def supported_keys(self) -> set[str]:
        return set(self.KEYS)

    def apply(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        applied = {k: parameters[k] for k in self.KEYS if k in parameters}
        self.state.applied.update(applied)
        if self.target is not None and not self.state.dry_run:
            setattr(self.target, "_arop_params", {**getattr(self.target, "_arop_params", {}), **applied})
        return applied
