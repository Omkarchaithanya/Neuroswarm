"""
System-aware merge of two Pareto-optimal text candidates.

Official concept: GEPA merge strategy — combine module-level improvements
from two frontier parents based on which parent refined each component.

ArmCascade/AROP: merges prompt/policy text components only.
"""

from __future__ import annotations

from datetime import datetime, timezone

from neuroswarm_arm.evolution.reflection.gepa.candidate.models import (
    MergeEvent,
    TextCandidate,
    validate_text_components,
)


class SystemAwareMergeEngine:
    """Merge two parents: prefer component text that changed vs shared ancestor seed."""

    def __init__(self) -> None:
        self._version = 0

    def merge(
        self,
        parent_a: TextCandidate,
        parent_b: TextCandidate,
        *,
        seed: TextCandidate | None = None,
    ) -> TextCandidate:
        keys = sorted(set(parent_a.components) | set(parent_b.components))
        if seed is None:
            # Prefer A's text when A differs from B; else B
            merged: dict[str, str] = {}
            from_a: list[str] = []
            from_b: list[str] = []
            for k in keys:
                va = parent_a.components.get(k, "")
                vb = parent_b.components.get(k, "")
                if va and (not vb or len(va) >= len(vb)):
                    merged[k] = va
                    from_a.append(k)
                else:
                    merged[k] = vb or va
                    from_b.append(k)
        else:
            merged = {}
            from_a = []
            from_b = []
            for k in keys:
                seed_v = seed.components.get(k, "")
                va = parent_a.components.get(k, seed_v)
                vb = parent_b.components.get(k, seed_v)
                # Prefer parent that actually mutated away from seed
                if va != seed_v and vb == seed_v:
                    merged[k] = va
                    from_a.append(k)
                elif vb != seed_v and va == seed_v:
                    merged[k] = vb
                    from_b.append(k)
                elif va != seed_v and vb != seed_v:
                    # Both mutated — pick higher mean-score parent for this key
                    if parent_a.mean_score() >= parent_b.mean_score():
                        merged[k] = va
                        from_a.append(k)
                    else:
                        merged[k] = vb
                        from_b.append(k)
                else:
                    merged[k] = seed_v or va or vb
                    from_a.append(k)

        merged = validate_text_components(merged)
        self._version += 1
        event = MergeEvent(
            at=datetime.now(timezone.utc),
            parent_a=parent_a.id,
            parent_b=parent_b.id,
            rationale="system_aware_merge",
            components_from_a=tuple(from_a),
            components_from_b=tuple(from_b),
        )
        return TextCandidate.create(
            merged,
            version=f"m{self._version}",
            parent_ids=(parent_a.id, parent_b.id),
            metadata={"strategy": "system_aware_merge"},
            mutation_history=parent_a.mutation_history + parent_b.mutation_history,
            merge_history=parent_a.merge_history + parent_b.merge_history + (event,),
        )
