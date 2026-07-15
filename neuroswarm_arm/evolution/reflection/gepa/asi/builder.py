"""
ASIBuilder — assemble Actionable Side Information for GEPA reflection.

Official concept: ASI / reflective dataset rows fed to the teacher LLM
(``make_reflective_dataset``). Analogous to gradients for text evolution.

ArmCascade/AROP: consolidates ObservationProviders + profiling; Performix
is evidence only and never mutates policy.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from neuroswarm_arm.evolution.reflection.gepa.asi.schema import (
    ActionableSideInformation,
    ReflectiveRecord,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ASIBuilder:
    """Build structured GEPA evidence from heterogeneous runtime signals."""

    SOURCE_KEYS = (
        "performix",
        "otel",
        "prometheus",
        "scheduler",
        "cascade",
        "governor",
        "tool_calls",
        "mem0",
        "reasoning",
        "compression",
        "routing",
        "tokens",
        "latency",
        "ttft",
        "tps",
        "kv",
        "context",
        "failures",
        "retries",
        "tool_outputs",
        "model_selection",
        "backend_selection",
        "budget",
        "profiling",
    )

    def build(
        self,
        *,
        episode_id: str | None = None,
        observations: Sequence[Mapping[str, Any]] | None = None,
        metrics: Mapping[str, float] | None = None,
        trajectories: Sequence[Mapping[str, Any]] | None = None,
        profiling_asi: Sequence[Mapping[str, Any]] | None = None,
        mem0_snippets: Sequence[str] | None = None,
        extras: Mapping[str, Any] | None = None,
    ) -> ActionableSideInformation:
        eid = episode_id or f"asi_{uuid.uuid4().hex[:10]}"
        agg: dict[str, float] = dict(metrics or {})
        sources: list[str] = []
        records: list[ReflectiveRecord] = []
        raw: dict[str, Any] = dict(extras or {})

        for obs in observations or []:
            src = str(obs.get("source", "runtime"))
            sources.append(src)
            m = obs.get("metrics") or {}
            if isinstance(m, Mapping):
                for k, v in m.items():
                    try:
                        agg[str(k)] = float(v)
                    except (TypeError, ValueError):
                        continue
            labels = obs.get("labels") or {}
            payload = obs.get("payload") or {}
            feedback = self._feedback_from_metrics(src, m if isinstance(m, Mapping) else {})
            records.append(
                ReflectiveRecord(
                    Inputs={"source": src, "labels": json.dumps(dict(labels), default=str)[:500]},
                    Generated_Outputs=json.dumps(payload, default=str)[:1000] if payload else "{}",
                    Feedback=feedback,
                    score=float(agg.get("reward_scalar", agg.get("accept_rate", 0.0))),
                    metrics={k: float(v) for k, v in (m.items() if isinstance(m, Mapping) else []) if _is_float(v)},
                )
            )

        if profiling_asi:
            sources.append("profiling")
            for item in profiling_asi:
                obs_vec = item.get("observation") or {}
                for k, v in obs_vec.items():
                    try:
                        agg[f"profile_{k}"] = float(v)
                    except (TypeError, ValueError):
                        continue
                recs = item.get("recommendations") or []
                records.append(
                    ReflectiveRecord(
                        Inputs={
                            "profile_id": str(item.get("profile_id", "")),
                            "backend": str(item.get("backend", "")),
                            "quantization": str(item.get("quantization", "")),
                        },
                        Generated_Outputs=json.dumps(obs_vec, default=str)[:1000],
                        Feedback="; ".join(str(r) for r in recs)
                        or f"Profile backend={item.get('backend')} ipc={obs_vec.get('ipc', 'n/a')}",
                        score=0.0,
                        metrics={k: float(v) for k, v in obs_vec.items() if _is_float(v)},
                        extras={"source": "profiling"},
                    )
                )

        for traj in trajectories or []:
            sources.append("trajectory")
            records.append(
                ReflectiveRecord(
                    Inputs={
                        "input": str(traj.get("input", traj.get("Inputs", "")))[:800],
                        "component": str(traj.get("component", "system_prompt")),
                    },
                    Generated_Outputs=str(traj.get("output", traj.get("Generated Outputs", "")))[:1200],
                    Feedback=str(
                        traj.get("feedback")
                        or traj.get("Feedback")
                        or traj.get("errors")
                        or "trajectory"
                    )[:1200],
                    score=float(traj.get("score", 0.0) or 0.0),
                    metrics={k: float(v) for k, v in (traj.get("metrics") or {}).items() if _is_float(v)},
                )
            )

        if mem0_snippets:
            sources.append("mem0")
            for snip in mem0_snippets:
                records.append(
                    ReflectiveRecord(
                        Inputs={"memory": "evolution"},
                        Generated_Outputs=snip[:800],
                        Feedback="Mem0 evolution history snippet",
                        score=0.0,
                        extras={"source": "mem0"},
                    )
                )

        # Synthesize aggregate feedback covering planned ASI dimensions
        records.append(self._aggregate_record(agg))
        sources = tuple(dict.fromkeys(sources))
        return ActionableSideInformation(
            episode_id=eid,
            collected_at=_utcnow(),
            sources=sources,
            metrics=agg,
            records=tuple(records),
            raw=raw,
        )

    def from_aggregator_snapshot(
        self,
        snapshot_providers: Mapping[str, Mapping[str, float]],
        *,
        aggregate: Mapping[str, float] | None = None,
        profiling_asi: Sequence[Mapping[str, Any]] | None = None,
    ) -> ActionableSideInformation:
        observations = [
            {"source": name, "metrics": dict(metrics), "labels": {"layer": "observation"}}
            for name, metrics in snapshot_providers.items()
        ]
        return self.build(
            observations=observations,
            metrics=aggregate,
            profiling_asi=profiling_asi,
        )

    def _aggregate_record(self, metrics: Mapping[str, float]) -> ReflectiveRecord:
        latency = metrics.get("latency_ms", metrics.get("ascr_latency_ms", 0.0))
        accept = metrics.get("accept_rate", metrics.get("ascr_accept_rate", 0.0))
        cost = metrics.get("cost_usd", 0.0)
        kv = metrics.get("kv_pressure", metrics.get("kv_usage", 0.0))
        tokens = metrics.get("reasoning_tokens", metrics.get("tokens", 0.0))
        feedback = (
            f"Latency={latency:.1f}ms accept={accept:.3f} cost={cost:.4f} "
            f"kv={kv:.3f} reasoning_tokens={tokens:.0f}. "
            "Use this evidence to improve textual prompts/policies only — "
            "do not change NUMA, threads, or kernels."
        )
        return ReflectiveRecord(
            Inputs={"aggregator": "ASIBuilder"},
            Generated_Outputs="aggregate",
            Feedback=feedback,
            score=float(metrics.get("reward_scalar", accept)),
            metrics=dict(metrics),
            extras={"source": "aggregate"},
        )

    @staticmethod
    def _feedback_from_metrics(source: str, metrics: Mapping[str, Any]) -> str:
        bits = [f"source={source}"]
        for key in (
            "latency_ms",
            "ascr_latency_ms",
            "ttft_ms",
            "tps",
            "accept_rate",
            "ascr_accept_rate",
            "kv_pressure",
            "cost_usd",
            "cpu_util",
            "energy_joules",
        ):
            if key in metrics:
                try:
                    bits.append(f"{key}={float(metrics[key]):.4g}")
                except (TypeError, ValueError):
                    continue
        return "; ".join(bits)


def _is_float(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
