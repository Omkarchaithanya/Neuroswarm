"""DI factory for ASCR."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from neuroswarm_arm.runtime.armcascade.arm.adapters import ArmRuntimeAdapter, PerformixHook
from neuroswarm_arm.runtime.armcascade.config.loader import (
    load_ascr_config,
    parse_escalation_graphs,
)
from neuroswarm_arm.runtime.armcascade.engine import ASCREngine
from neuroswarm_arm.runtime.armcascade.metrics.prometheus import ASCRMetrics
from neuroswarm_arm.runtime.armcascade.plugins import load_plugins
from neuroswarm_arm.runtime.armcascade.proposal.registry import (
    ProposalRegistry,
    VerifierRegistry,
)


def build_ascr(
    registry: Any,
    *,
    config: Mapping[str, Any] | None = None,
    config_root: Path | None = None,
    metrics_bridge: Any | None = None,
    legacy_metrics: Any | None = None,
    dipa_cascade_cfg: Mapping[str, Any] | None = None,
    memory_connector: Any | None = None,
) -> ASCREngine:
    """Construct a fully wired ASCREngine."""
    load_plugins()
    cfg = dict(config or load_ascr_config(config_root))

    # Merge legacy dipa cascade.yaml knobs when provided.
    if dipa_cascade_cfg:
        cfg = _merge_dipa_cascade(cfg, dipa_cascade_cfg)

    graphs = parse_escalation_graphs(cfg.get("escalation_graphs"))
    metrics = ASCRMetrics(
        bridge=metrics_bridge,
        alias_dipa=bool((cfg.get("telemetry") or {}).get("alias_dipa_cascade", True)),
    )
    arm = ArmRuntimeAdapter(cfg)
    return ASCREngine(
        config=cfg,
        registry=registry,
        graphs=graphs,
        proposers=ProposalRegistry(),
        verifiers=VerifierRegistry(),
        metrics=metrics,
        arm=arm,
        performix=PerformixHook(),
        legacy_metrics=legacy_metrics,
        memory_connector=memory_connector,
    )


def _merge_dipa_cascade(
    cfg: dict[str, Any], dipa: Mapping[str, Any]
) -> dict[str, Any]:
    out = dict(cfg)
    if dipa.get("tiers"):
        out["tiers"] = list(dipa["tiers"])
    if dipa.get("confidence"):
        out["confidence"] = {
            **dict(out.get("confidence") or {}),
            **dict(dipa["confidence"]),
        }
    spec = dict(dipa.get("speculation") or {})
    ascr = dict(dipa.get("ascr") or {})
    defaults = dict(out.get("defaults") or {})
    if spec:
        if "draft_len" in spec or "draft_max" in spec:
            defaults["draft_len"] = int(
                spec.get("draft_len", spec.get("draft_max", defaults.get("draft_len", 8)))
            )
        if "accept_threshold" in spec:
            defaults["accept_threshold"] = float(spec["accept_threshold"])
        strategies = dict(out.get("strategies") or {})
        ss = dict(strategies.get("self_speculation") or {})
        ss.update(
            {
                "ngram_size": int(spec.get("ngram_size", ss.get("ngram_size", 24))),
                "draft_min": int(spec.get("draft_min", ss.get("draft_min", 4))),
                "draft_max": int(spec.get("draft_max", ss.get("draft_max", 48))),
                "enabled": bool(spec.get("enabled", True)),
            }
        )
        strategies["self_speculation"] = ss
        out["strategies"] = strategies
        if spec.get("strategy"):
            defaults["proposal_strategy"] = str(spec["strategy"])
        if spec.get("verify_strategy"):
            defaults["verify_strategy"] = str(spec["verify_strategy"])
        if spec.get("graph"):
            out["default_graph"] = str(spec["graph"])
    if ascr:
        if ascr.get("strategy"):
            defaults["proposal_strategy"] = str(ascr["strategy"])
        if ascr.get("verify_strategy"):
            defaults["verify_strategy"] = str(ascr["verify_strategy"])
        if ascr.get("graph"):
            out["default_graph"] = str(ascr["graph"])
        if ascr.get("accept_threshold") is not None:
            defaults["accept_threshold"] = float(ascr["accept_threshold"])
    out["defaults"] = defaults
    return out
