"""
NexusGEPAAdapter — bridge NEXUS runtime ↔ GEPA text evolution.

Official concept: ``gepa.core.adapter.GEPAAdapter``
(https://github.com/gepa-ai/gepa/blob/main/src/gepa/core/adapter.py)

Responsibilities mirrored:
1. ``evaluate`` — run candidate text components on a data batch
2. ``make_reflective_dataset`` — build ASI rows for teacher LM

ArmCascade/AROP: adapter never touches NUMA/threads/kernels; optional soft
import of official ``gepa`` for offline jobs only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from neuroswarm_arm.evolution.reflection.gepa.asi.builder import ASIBuilder
from neuroswarm_arm.evolution.reflection.gepa.asi.schema import ActionableSideInformation
from neuroswarm_arm.evolution.reflection.gepa.candidate.models import TextCandidate, validate_text_components
from neuroswarm_arm.evolution.reflection.gepa.evaluation.batch import EvaluationBatch


class GEPAAdapterProtocol(Protocol):
    """Local mirror of official GEPAAdapter Protocol."""

    def evaluate(
        self,
        batch: list[dict[str, Any]],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch[dict[str, Any], dict[str, Any]]: ...

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch[dict[str, Any], dict[str, Any]],
        components_to_update: list[str],
    ) -> Mapping[str, Sequence[Mapping[str, Any]]]: ...


class NexusGEPAAdapter:
    """
    Default NEXUS adapter.

    Evaluation is pluggable via ``eval_fn``; default heuristic scores text
    candidates using length + keyword heuristics suitable for CI.
    """

    def __init__(
        self,
        *,
        asi_builder: ASIBuilder | None = None,
        eval_fn: Any | None = None,
        base_asi: ActionableSideInformation | None = None,
    ) -> None:
        self.asi_builder = asi_builder or ASIBuilder()
        self.eval_fn = eval_fn
        self.base_asi = base_asi

    def evaluate(
        self,
        batch: list[dict[str, Any]],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch[dict[str, Any], dict[str, Any]]:
        comps = validate_text_components(candidate)
        if self.eval_fn is not None:
            return self.eval_fn(batch, comps, capture_traces=capture_traces)

        outputs: list[dict[str, Any]] = []
        scores: list[float] = []
        trajectories: list[dict[str, Any]] = []
        objective_scores: list[dict[str, float]] = []

        prompt = "\n".join(comps.values())
        prompt_len = float(len(prompt))
        has_lesson = 1.0 if "[GEPA lesson]" in prompt else 0.0

        for i, example in enumerate(batch):
            # Heuristic: reward short-ish prompts with lessons; penalize empty
            accuracy = 0.4 + 0.3 * has_lesson
            if prompt.strip():
                accuracy += 0.1
            latency_penalty = min(prompt_len / 5000.0, 0.3)
            score = max(0.0, accuracy - latency_penalty)
            expected = str(example.get("expected", example.get("answer", "")))
            query = str(example.get("input", example.get("question", f"ex{i}")))
            out = {"example_id": example.get("id", i), "preview": prompt[:120]}
            outputs.append(out)
            scores.append(score)
            obj = {
                "accuracy": accuracy,
                "latency": prompt_len,  # proxy
                "cost": prompt_len / 10000.0,
                "reasoning_tokens": prompt_len / 4.0,
                "tool_calls": 0.0,
                "compression_ratio": 1.0,
                "prompt_length": prompt_len,
                "context_length": float(len(query)),
                "memory": 0.0,
                "cpu": 0.0,
                "acceptance_rate": accuracy,
            }
            objective_scores.append(obj)
            if capture_traces:
                trajectories.append(
                    {
                        "input": query,
                        "output": out["preview"],
                        "expected": expected,
                        "errors": "" if score > 0.3 else "low_score",
                        "score": score,
                        "metrics": obj,
                        "component": next(iter(comps), "system_prompt"),
                    }
                )

        return EvaluationBatch(
            outputs=outputs,
            scores=scores,
            trajectories=trajectories if capture_traces else None,
            objective_scores=objective_scores,
            num_metric_calls=len(batch),
        )

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch[dict[str, Any], dict[str, Any]],
        components_to_update: list[str],
    ) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        comps = components_to_update or list(candidate.keys()) or ["system_prompt"]
        asi = self.base_asi
        trajs = eval_batch.trajectories or []
        records_by_comp: dict[str, list[dict[str, Any]]] = {c: [] for c in comps}

        for idx, score in enumerate(eval_batch.scores):
            traj = trajs[idx] if idx < len(trajs) else {}
            feedback = str(traj.get("errors") or "")
            if not feedback:
                feedback = f"Score: {score:.3f}."
            if asi is not None:
                feedback = f"{feedback} ASI: {asi.feedback_text()[:400]}"
            row = {
                "Inputs": {
                    "input": str(traj.get("input", "")),
                    "candidate_preview": {k: candidate.get(k, "")[:200] for k in comps},
                },
                "Generated Outputs": str(traj.get("output", eval_batch.outputs[idx] if idx < len(eval_batch.outputs) else {})),
                "Feedback": feedback,
                "score": float(score),
            }
            if eval_batch.objective_scores and idx < len(eval_batch.objective_scores):
                row["metrics"] = dict(eval_batch.objective_scores[idx])
            for c in comps:
                records_by_comp[c].append(row)

        # If no trajectories, still emit one ASI-backed row per component
        if not eval_batch.scores:
            for c in comps:
                records_by_comp[c].append(
                    {
                        "Inputs": {"component": c},
                        "Generated Outputs": candidate.get(c, ""),
                        "Feedback": asi.feedback_text() if asi else "no evaluation",
                        "score": 0.0,
                    }
                )
        return records_by_comp


class OfficialGEPABridge:
    """
    Optional soft bridge to ``gepa.optimize`` when the package is installed.

    Maps to official: ``gepa.api.optimize`` / ``gepa.optimize``.
    Never required for CI — absence is not an error.
    """

    def __init__(self) -> None:
        self.available = False
        self._optimize = None
        try:
            import gepa  # type: ignore

            self._optimize = getattr(gepa, "optimize", None)
            self.available = callable(self._optimize)
        except Exception:
            self.available = False

    def optimize(self, **kwargs: Any) -> Any:
        if not self.available or self._optimize is None:
            raise RuntimeError("official gepa package not installed")
        return self._optimize(**kwargs)
