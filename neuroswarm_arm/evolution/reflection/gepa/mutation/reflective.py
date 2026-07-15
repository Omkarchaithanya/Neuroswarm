"""
Reflective mutation — LLM (or mock) proposes improved text components.

Official concept: reflective mutation proposer (GEPA engine iteration);
teacher LM reads reflective dataset and emits new component texts.

ArmCascade/AROP: mutates prompts/policies only; never hardware knobs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from neuroswarm_arm.evolution.reflection.gepa.asi.schema import ActionableSideInformation
from neuroswarm_arm.evolution.reflection.gepa.candidate.models import (
    MutationEvent,
    TextCandidate,
    validate_text_components,
)


class ReflectionLM(ABC):
    """Teacher LLM port for proposing new component texts."""

    @abstractmethod
    def propose(
        self,
        candidate: Mapping[str, str],
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        raise NotImplementedError


class MockReflectionLM(ReflectionLM):
    """Deterministic teacher for CI — appends lesson tags from ASI feedback."""

    def propose(
        self,
        candidate: Mapping[str, str],
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        lessons: list[str] = []
        for comp, rows in reflective_dataset.items():
            for row in rows[:3]:
                fb = str(row.get("Feedback", ""))[:200]
                if fb:
                    lessons.append(fb)
        lesson_block = " | ".join(lessons)[:400] or "stabilize quality and reduce latency"
        out = dict(candidate)
        for comp in components_to_update:
            base = out.get(comp, "")
            tag = f"\n\n[GEPA lesson]: {lesson_block}"
            if "[GEPA lesson]" in base:
                # Refresh lesson line
                head = base.split("[GEPA lesson]")[0].rstrip()
                out[comp] = f"{head}\n\n[GEPA lesson]: {lesson_block}"
            else:
                out[comp] = f"{base}{tag}" if base else f"You are a careful assistant.\n[GEPA lesson]: {lesson_block}"
        return validate_text_components(out)


class ReflectiveMutationEngine:
    """Produce a child TextCandidate from parent + ASI via ReflectionLM."""

    def __init__(self, lm: ReflectionLM | None = None) -> None:
        self.lm = lm or MockReflectionLM()
        self._version = 0

    def mutate(
        self,
        parent: TextCandidate,
        *,
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str] | None = None,
        asi: ActionableSideInformation | None = None,
    ) -> TextCandidate:
        comps = list(components_to_update or list(parent.components.keys()) or ["system_prompt"])
        if not comps:
            comps = ["system_prompt"]
        # Ensure keys exist
        seed = dict(parent.components)
        for c in comps:
            seed.setdefault(c, "You are a helpful assistant.")
        proposed = self.lm.propose(seed, reflective_dataset, comps)
        self._version += 1
        rationale = asi.feedback_text()[:300] if asi else "reflective_mutation"
        event = MutationEvent(
            at=datetime.now(timezone.utc),
            parent_id=parent.id,
            rationale=rationale,
            components_updated=tuple(comps),
        )
        return TextCandidate.create(
            proposed,
            version=f"v{self._version}",
            parent_ids=(parent.id,),
            metadata={"strategy": "reflective_mutation"},
            mutation_history=parent.mutation_history + (event,),
            merge_history=parent.merge_history,
        )
