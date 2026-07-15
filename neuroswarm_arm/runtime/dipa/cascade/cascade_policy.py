"""Typed cascade policy loaded from ``cascade.yaml``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(slots=True)
class TierPolicy:
    id: int
    backend: str
    model: str
    acceptance_threshold: float = 0.85


@dataclass(slots=True)
class SpeculationPolicy:
    enabled: bool = False
    self_speculation: bool = False
    ngram_size: int = 24
    draft_min: int = 12
    draft_max: int = 48


@dataclass(slots=True)
class CascadeFallbackPolicy:
    on_all_tiers_fail: str = "degraded"
    degraded_message: str = "Inference temporarily degraded."


@dataclass(slots=True)
class CascadePolicy:
    """Cascade tier ladder + confidence / speculation / fallback knobs."""

    tiers: list[TierPolicy] = field(default_factory=list)
    confidence: dict[str, Any] = field(default_factory=dict)
    speculation: SpeculationPolicy = field(default_factory=SpeculationPolicy)
    fallback: CascadeFallbackPolicy = field(default_factory=CascadeFallbackPolicy)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> CascadePolicy:
        raw = dict(data or {})
        tiers = [_parse_tier(item) for item in (raw.get("tiers") or [])]
        tiers.sort(key=lambda t: t.id)

        conf = dict(raw.get("confidence") or {})
        if "uncertainty_phrases" in conf and isinstance(
            conf["uncertainty_phrases"], Sequence
        ):
            conf["uncertainty_phrases"] = [str(p) for p in conf["uncertainty_phrases"]]

        spec_raw = dict(raw.get("speculation") or {})
        speculation = SpeculationPolicy(
            enabled=bool(spec_raw.get("enabled", False)),
            self_speculation=bool(spec_raw.get("self_speculation", False)),
            ngram_size=int(spec_raw.get("ngram_size", 24)),
            draft_min=int(spec_raw.get("draft_min", 12)),
            draft_max=int(spec_raw.get("draft_max", 48)),
        )

        fb_raw = dict(raw.get("fallback") or {})
        fallback = CascadeFallbackPolicy(
            on_all_tiers_fail=str(fb_raw.get("on_all_tiers_fail", "degraded")),
            degraded_message=str(
                fb_raw.get("degraded_message", "Inference temporarily degraded.")
            ),
        )

        if not tiers:
            tiers = [
                TierPolicy(id=1, backend="tier1", model="tier1", acceptance_threshold=0.85),
                TierPolicy(id=2, backend="tier2", model="tier2", acceptance_threshold=0.5),
                TierPolicy(id=3, backend="tier3", model="tier3", acceptance_threshold=0.0),
            ]

        return cls(
            tiers=tiers,
            confidence=conf,
            speculation=speculation,
            fallback=fallback,
        )

    def tier_for(self, tier_id: int) -> TierPolicy | None:
        for tier in self.tiers:
            if tier.id == tier_id:
                return tier
        return None

    def tiers_from(self, start_tier: int) -> list[TierPolicy]:
        return [t for t in self.tiers if t.id >= int(start_tier)]


def _parse_tier(item: Mapping[str, Any] | Any) -> TierPolicy:
    if not isinstance(item, Mapping):
        raise TypeError(f"tier entry must be a mapping, got {type(item)!r}")
    return TierPolicy(
        id=int(item.get("id", 0)),
        backend=str(item.get("backend", f"tier{item.get('id', 0)}")),
        model=str(item.get("model", item.get("backend", ""))),
        acceptance_threshold=float(item.get("acceptance_threshold", 0.85)),
    )
