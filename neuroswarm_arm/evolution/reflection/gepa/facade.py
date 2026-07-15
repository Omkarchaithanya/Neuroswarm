"""
GEPAFacade — public API for the GEPA reflection subsystem.

Official workflow surface (reflect / mutate / merge / evaluate /
pareto_select / candidate_pool) without hard-coupling AROP to the
``gepa`` PyPI package.

ArmCascade/AROP: text-only evolution; Approval required before deploy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from neuroswarm_arm.evolution.reflection.gepa.adapter import NexusGEPAAdapter, OfficialGEPABridge
from neuroswarm_arm.evolution.reflection.gepa.asi.builder import ASIBuilder
from neuroswarm_arm.evolution.reflection.gepa.asi.schema import ActionableSideInformation
from neuroswarm_arm.evolution.reflection.gepa.candidate.models import TextCandidate
from neuroswarm_arm.evolution.reflection.gepa.candidate.pool import CandidatePool
from neuroswarm_arm.evolution.reflection.gepa.evaluation.batch import EvaluationBatch
from neuroswarm_arm.evolution.reflection.gepa.merge.system_aware import SystemAwareMergeEngine
from neuroswarm_arm.evolution.reflection.gepa.mutation.reflective import (
    MockReflectionLM,
    ReflectionLM,
    ReflectiveMutationEngine,
)
from neuroswarm_arm.evolution.reflection.gepa.pareto.front import ParetoFront


@dataclass
class GEPAOptimizeResult:
    best: TextCandidate | None
    frontier: list[TextCandidate] = field(default_factory=list)
    iterations: int = 0
    accepted: int = 0
    message: str = ""


class GEPAFacade:
    """
    Facade methods required by the alignment plan:

    - reflect()
    - mutate()
    - merge()
    - evaluate()
    - pareto_select()
    - candidate_pool()
    """

    def __init__(
        self,
        *,
        pool: CandidatePool | None = None,
        adapter: NexusGEPAAdapter | None = None,
        mutation: ReflectiveMutationEngine | None = None,
        merge_engine: SystemAwareMergeEngine | None = None,
        pareto: ParetoFront | None = None,
        asi_builder: ASIBuilder | None = None,
        reflection_lm: ReflectionLM | None = None,
        work_dir: Path | None = None,
    ) -> None:
        work = work_dir or Path("work/arop/gepa")
        self.asi_builder = asi_builder or ASIBuilder()
        self.pool = pool or CandidatePool(store_path=work / "candidate_pool.json")
        self.adapter = adapter or NexusGEPAAdapter(asi_builder=self.asi_builder)
        self.mutation = mutation or ReflectiveMutationEngine(lm=reflection_lm or MockReflectionLM())
        self.merge_engine = merge_engine or SystemAwareMergeEngine()
        self.pareto = pareto or ParetoFront()
        self.bridge = OfficialGEPABridge()
        self._last_asi: ActionableSideInformation | None = None
        self._rng = random.Random(0)

    def candidate_pool(self) -> CandidatePool:
        return self.pool

    def reflect(
        self,
        *,
        asi: ActionableSideInformation | None = None,
        observations: Sequence[Mapping[str, Any]] | None = None,
        metrics: Mapping[str, float] | None = None,
        profiling_asi: Sequence[Mapping[str, Any]] | None = None,
    ) -> ActionableSideInformation:
        """Build ASI / reflective evidence (official: make_reflective_dataset inputs)."""
        if asi is not None:
            self._last_asi = asi
            self.adapter.base_asi = asi
            return asi
        built = self.asi_builder.build(
            observations=observations,
            metrics=metrics,
            profiling_asi=profiling_asi,
        )
        self._last_asi = built
        self.adapter.base_asi = built
        return built

    def evaluate(
        self,
        candidate: TextCandidate | dict[str, str],
        batch: list[dict[str, Any]],
        *,
        capture_traces: bool = True,
    ) -> EvaluationBatch[dict[str, Any], dict[str, Any]]:
        comps = candidate.components if isinstance(candidate, TextCandidate) else candidate
        return self.adapter.evaluate(batch, dict(comps), capture_traces=capture_traces)

    def mutate(
        self,
        parent: TextCandidate,
        *,
        batch: list[dict[str, Any]] | None = None,
        components_to_update: list[str] | None = None,
    ) -> TextCandidate:
        data = batch or [{"id": 0, "input": "smoke", "expected": ""}]
        eval_batch = self.adapter.evaluate(data, dict(parent.components), capture_traces=True)
        comps = components_to_update or list(parent.components.keys()) or ["system_prompt"]
        reflective = self.adapter.make_reflective_dataset(dict(parent.components), eval_batch, comps)
        child = self.mutation.mutate(
            parent,
            reflective_dataset=reflective,
            components_to_update=comps,
            asi=self._last_asi,
        )
        self.pool.add(child)
        return child

    def merge(self, parent_a: TextCandidate, parent_b: TextCandidate) -> TextCandidate:
        child = self.merge_engine.merge(parent_a, parent_b)
        self.pool.add(child)
        return child

    def pareto_select(self) -> TextCandidate | None:
        self.pareto.update(self.pool.all())
        return self.pareto.select(rng=self._rng)

    def run_local_loop(
        self,
        seed: TextCandidate | dict[str, str],
        *,
        trainset: list[dict[str, Any]],
        valset: list[dict[str, Any]] | None = None,
        max_iterations: int = 3,
        use_merge: bool = True,
    ) -> GEPAOptimizeResult:
        """
        Faithful local Genetic-Pareto loop (CI-safe).

        Official: Select → Execute → Reflect → Mutate → Accept → Pareto;
        optional system-aware merge.
        """
        val = valset or trainset
        if isinstance(seed, dict):
            seed_c = TextCandidate.create(seed, version="seed")
        else:
            seed_c = seed
        self.pool.add(seed_c)

        seed_eval = self.adapter.evaluate(val, dict(seed_c.components), capture_traces=True)
        seed_scored = self._apply_eval_scores(seed_c, seed_eval, val)
        self.pool.replace_same_id(seed_scored)
        self.pareto.update(self.pool.all())

        accepted = 0
        for i in range(max_iterations):
            parent = self.pareto_select() or seed_scored
            child = self.mutate(parent, batch=trainset)
            parent_mb = self.adapter.evaluate(trainset, dict(parent.components), capture_traces=False)
            child_mb = self.adapter.evaluate(trainset, dict(child.components), capture_traces=False)
            if child_mb.sum_scores() >= parent_mb.sum_scores():
                child_val = self.adapter.evaluate(val, dict(child.components), capture_traces=True)
                child_scored = self._apply_eval_scores(child, child_val, val)
                self.pool.replace_same_id(child_scored)
                self.pareto.update(self.pool.all())
                accepted += 1
                seed_scored = child_scored

            if use_merge and len(self.pareto.members()) >= 2:
                members = self.pareto.members()
                a, b = members[0], members[1]
                merged = self.merge(a, b)
                merged_mb = self.adapter.evaluate(trainset, dict(merged.components), capture_traces=False)
                base = max(a.mean_score(), b.mean_score())
                if merged_mb.mean_score() >= base:
                    merged_val = self.adapter.evaluate(val, dict(merged.components), capture_traces=True)
                    merged_scored = self._apply_eval_scores(merged, merged_val, val)
                    self.pool.replace_same_id(merged_scored)
                    self.pareto.update(self.pool.all())
                    accepted += 1

        frontier = self.pareto.members()
        best = max(frontier, key=lambda c: c.mean_score()) if frontier else seed_scored
        return GEPAOptimizeResult(
            best=best,
            frontier=frontier,
            iterations=max_iterations,
            accepted=accepted,
            message=f"local_loop accepted={accepted} frontier={len(frontier)}",
        )

    def _apply_eval_scores(
        self,
        candidate: TextCandidate,
        eval_batch: EvaluationBatch[dict[str, Any], dict[str, Any]],
        batch: list[dict[str, Any]],
    ) -> TextCandidate:
        per_task: dict[str, float] = {}
        for i, score in enumerate(eval_batch.scores):
            key = str(batch[i].get("id", i)) if i < len(batch) else str(i)
            per_task[key] = float(score)
        obj_agg: dict[str, float] = {"aggregate": eval_batch.mean_score()}
        if eval_batch.objective_scores:
            keys = eval_batch.objective_scores[0].keys()
            for k in keys:
                vals = [o.get(k, 0.0) for o in eval_batch.objective_scores]
                obj_agg[str(k)] = sum(vals) / max(len(vals), 1)
        return candidate.with_scores(obj_agg, per_task_scores=per_task)
