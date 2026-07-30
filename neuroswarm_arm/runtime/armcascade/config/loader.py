"""ASCR configuration loaders (YAML + env overlay)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    EscalationEdge,
    EscalationGraph,
    EscalationNode,
    ThresholdSet,
)

_CONFIG_DIR = Path(__file__).resolve().parent


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        raise RuntimeError("PyYAML required to load ASCR config")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise TypeError(f"config root must be mapping: {path}")
    return dict(data)


def load_ascr_config(root: Path | None = None) -> dict[str, Any]:
    """Load ascr.yaml + strategies + tiers + graphs; apply NSA_ASCR_* overlays."""
    cfg_dir = root or _CONFIG_DIR
    master = _load_yaml(cfg_dir / "ascr.yaml")
    strategies = _load_yaml(cfg_dir / "strategies.yaml")
    tiers = _load_yaml(cfg_dir / "tiers.yaml")
    graphs = _load_yaml(cfg_dir / "escalation_graphs.yaml")

    merged: dict[str, Any] = {
        **master,
        "strategies": strategies.get("strategies", master.get("strategies", {})),
        "tiers": tiers.get("tiers", master.get("tiers", [])),
        "escalation_graphs": graphs.get("graphs", master.get("escalation_graphs", {})),
        "default_graph": graphs.get(
            "default_graph", master.get("default_graph", "default_linear")
        ),
    }
    return apply_env_overrides(merged)


def apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(cfg)
    if v := os.environ.get("NSA_ASCR_ENABLED"):
        out["enabled"] = v.strip().lower() in {"1", "true", "yes", "on"}
    if v := os.environ.get("NSA_ASCR_DEFAULT_PROPOSER"):
        out.setdefault("defaults", {})
        out["defaults"] = dict(out.get("defaults") or {})
        out["defaults"]["proposal_strategy"] = v.strip()
    if v := os.environ.get("NSA_ASCR_DEFAULT_VERIFIER"):
        out.setdefault("defaults", {})
        out["defaults"] = dict(out.get("defaults") or {})
        out["defaults"]["verify_strategy"] = v.strip()
    if v := os.environ.get("NSA_ASCR_DRAFT_LEN"):
        out.setdefault("defaults", {})
        out["defaults"] = dict(out.get("defaults") or {})
        out["defaults"]["draft_len"] = int(v)
    if v := os.environ.get("NSA_ASCR_ACCEPT_THRESHOLD"):
        out.setdefault("defaults", {})
        out["defaults"] = dict(out.get("defaults") or {})
        out["defaults"]["accept_threshold"] = float(v)
    if v := os.environ.get("NSA_ASCR_QUALITY_ACCEPT_THRESHOLD"):
        out.setdefault("defaults", {})
        out["defaults"] = dict(out.get("defaults") or {})
        out["defaults"]["quality_accept_threshold"] = float(v)
    if v := os.environ.get("NSA_ASCR_QUALITY_EARLY_ACCEPT"):
        out.setdefault("defaults", {})
        out["defaults"] = dict(out.get("defaults") or {})
        out["defaults"]["quality_early_accept_floor"] = float(v)
    if v := os.environ.get("NSA_ASCR_GRAPH"):
        out["default_graph"] = v.strip()
    if v := os.environ.get("NSA_ASCR_QUALITY_FALLBACK"):
        out["quality_cascade_fallback"] = v.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if v := os.environ.get("NSA_ASCR_TEXT_AGREE"):
        out["text_agree_accept"] = v.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if v := os.environ.get("NSA_ASCR_LOGITS_ENABLED"):
        out.setdefault("strategies", {})
        strategies = dict(out.get("strategies") or {})
        logits = dict(strategies.get("logits") or {})
        logits["enabled"] = v.strip().lower() in {"1", "true", "yes", "on"}
        strategies["logits"] = logits
        out["strategies"] = strategies
    if v := os.environ.get("NSA_ASCR_TAU_FLOOR"):
        out.setdefault("strategies", {})
        strategies = dict(out.get("strategies") or {})
        logits = dict(strategies.get("logits") or {})
        logits["tau_floor"] = float(v)
        strategies["logits"] = logits
        out["strategies"] = strategies
    if v := os.environ.get("NSA_ASCR_LOGITS_TOP_N"):
        out.setdefault("strategies", {})
        strategies = dict(out.get("strategies") or {})
        logits = dict(strategies.get("logits") or {})
        logits["top_n"] = int(v)
        strategies["logits"] = logits
        out["strategies"] = strategies
    if v := os.environ.get("NSA_ASCR_MAX_ROUNDS"):
        out.setdefault("defaults", {})
        out["defaults"] = dict(out.get("defaults") or {})
        out["defaults"]["max_rounds"] = int(v)
    return out


def default_thresholds(cfg: Mapping[str, Any] | None = None) -> ThresholdSet:
    d = dict((cfg or {}).get("defaults") or {})
    return ThresholdSet(
        draft_len=int(d.get("draft_len", 8)),
        accept_threshold=float(d.get("accept_threshold", 0.7)),
        verify_batch_size=int(d.get("verify_batch_size", 1)),
        escalate_threshold=float(d.get("escalate_threshold", 0.4)),
        speculation_depth=int(d.get("speculation_depth", 1)),
        max_rounds=int(d.get("max_rounds", 4)),
        quality_accept_threshold=float(
            d.get("quality_accept_threshold", d.get("accept_threshold", 0.55))
        ),
        quality_early_accept_floor=float(
            d.get(
                "quality_early_accept_floor",
                d.get("quality_accept_threshold", 0.52),
            )
        ),
    )


def parse_escalation_graphs(raw: Mapping[str, Any] | None) -> dict[str, EscalationGraph]:
    graphs: dict[str, EscalationGraph] = {}
    for name, body in dict(raw or {}).items():
        if not isinstance(body, Mapping):
            continue
        nodes: dict[str, EscalationNode] = {}
        for nid, nbody in dict(body.get("nodes") or {}).items():
            nb = dict(nbody or {})
            nodes[str(nid)] = EscalationNode(
                id=str(nid),
                kind=str(nb.get("kind", "tier")),
                tier_id=int(nb["tier_id"]) if nb.get("tier_id") is not None else None,
                metadata=dict(nb.get("metadata") or {}),
            )
        edges = [
            EscalationEdge(
                source=str(e.get("source", "")),
                target=str(e.get("target", "")),
                condition=str(e.get("condition", "always")),
                weight=float(e.get("weight", 1.0)),
            )
            for e in (body.get("edges") or [])
            if isinstance(e, Mapping)
        ]
        graphs[str(name)] = EscalationGraph(
            name=str(name),
            nodes=nodes,
            edges=edges,
            start=str(body.get("start", "tier1")),
        )
    if "default_linear" not in graphs:
        graphs["default_linear"] = _builtin_linear_graph()
    return graphs


def _builtin_linear_graph() -> EscalationGraph:
    return EscalationGraph(
        name="default_linear",
        start="tier1",
        nodes={
            "tier1": EscalationNode(id="tier1", kind="tier", tier_id=1),
            "tier2": EscalationNode(id="tier2", kind="tier", tier_id=2),
            "tier3": EscalationNode(id="tier3", kind="tier", tier_id=3),
            "accept": EscalationNode(id="accept", kind="accept"),
        },
        edges=[
            EscalationEdge("tier1", "accept", "high_confidence"),
            EscalationEdge("tier1", "tier2", "low_confidence"),
            EscalationEdge("tier2", "accept", "high_confidence"),
            EscalationEdge("tier2", "tier3", "low_confidence"),
            EscalationEdge("tier3", "accept", "always"),
        ],
    )


def reload_ascr_config(root: Path | None = None) -> dict[str, Any]:
    """Hot-reload entrypoint for ConfigurationManager hooks."""
    return load_ascr_config(root)
