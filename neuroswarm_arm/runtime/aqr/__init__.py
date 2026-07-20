"""AQR runtime package — adaptive quantization routing."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.aqr import QUANT_BY_ROLE, pick_quant
from neuroswarm_arm.runtime.aqr.runtime_config import load_aqr_config


def cascade_profile_for_tier(tier: int | str = 1) -> dict[str, Any]:
    """Return cascade_profiles.yaml floors/preferred quants for a tier."""
    cfg = load_aqr_config()
    tiers = dict((cfg.cascade_profiles or {}).get("tiers") or {})
    key = int(tier) if str(tier).isdigit() else tier
    raw = tiers.get(key) or tiers.get(str(key)) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def pick_quant_for_tier(tier: int = 1, *, agent_role: str = "reasoning", workload_class: str | None = None) -> str:
    """Pick quant using cascade_profiles preferred_quants when present."""
    profile = cascade_profile_for_tier(tier)
    preferred = profile.get("preferred_quants") or []
    if isinstance(preferred, list) and preferred:
        return str(preferred[0])
    return pick_quant(agent_role, workload_class)


def pick_quant_primary(agent_role: str, workload_class: str | None = None) -> str:
    """Primary quant picker used by DIPA — honors cascade_profiles tier-1 floors."""
    # Map roles to cascade tiers: tool/class → 1, code/reason → 2 default preference.
    role = (agent_role or "").lower()
    wl = (workload_class or "").lower()
    tier = 1
    if role in {"reasoning", "code"} or wl in {"reasoning", "coding", "code"}:
        tier = 2
    if role in {"summarization", "tool_call", "classification"} or wl in {
        "tool_calling",
        "classification",
        "summarization",
    }:
        tier = 1
    return pick_quant_for_tier(tier, agent_role=agent_role, workload_class=workload_class)


def plan_metadata_from_profiles(tier: int = 1) -> dict[str, Any]:
    """Metadata consumed by ASCR policy / ExecutionPlan."""
    profile = cascade_profile_for_tier(tier)
    if not profile:
        return {}
    preferred = profile.get("preferred_quants") or []
    quant = str(preferred[0]) if preferred else ""
    return {
        "aqr_cascade_tier": int(tier),
        "aqr_quality_floor": float(profile.get("quality_floor", 0.0) or 0.0),
        "aqr_max_bits": float(profile.get("max_bits", 0.0) or 0.0),
        "aqr_preferred_quants": list(preferred),
        # Nested under quant dict so QuantRouter can set ["resolved"] safely.
        "quant": {"aqr_preferred": quant} if quant else {},
        "aqr_prefer_fast": 1.0 if float(profile.get("quality_floor", 1.0) or 1.0) < 0.5 else 0.0,
    }


__all__ = [
    "QUANT_BY_ROLE",
    "cascade_profile_for_tier",
    "pick_quant",
    "pick_quant_for_tier",
    "pick_quant_primary",
    "plan_metadata_from_profiles",
]
