"""Protocol port contract tests — interfaces only, no peer concretes."""

from __future__ import annotations

from typing import Any, Mapping

from neuroswarm_arm.runtime.resilience import (
    IArmoraResiliencePort,
    IDipaResiliencePort,
    IExperienceStorePort,
    IPerformixResiliencePort,
    build_resilience_engine,
)

from .conftest import make_catalog, make_plan, make_signals


class _Armora:
    def envelope_id(self) -> str:
        return "env_1"

    def remaining(self) -> Mapping[str, float | None]:
        return {"cost_usd": 0.05}

    def is_frozen(self) -> bool:
        return True


class _Dipa:
    def __init__(self) -> None:
        self.patches: list[dict] = []

    def active_plan(self, execution_id: str) -> Mapping[str, Any]:
        return {"execution_id": execution_id, "model": "Qwen3-8B"}

    def apply_plan_patch(self, execution_id: str, patch: Mapping[str, Any]) -> None:
        self.patches.append({"execution_id": execution_id, **dict(patch)})


class _Experience:
    def __init__(self) -> None:
        self.stored: list[Any] = []

    def store_snapshot(self, snapshot: Any) -> str:
        self.stored.append(snapshot)
        return f"snap_{len(self.stored)}"

    def load_snapshot(self, handle: str) -> Any:
        return {"handle": handle}


class _Performix:
    def __init__(self) -> None:
        self.samples: list[dict] = []

    def record_resilience_sample(
        self,
        execution_id: str,
        *,
        quality_delta: float,
        latency_delta: float,
        cost_delta: float,
    ) -> None:
        self.samples.append(
            {
                "execution_id": execution_id,
                "quality_delta": quality_delta,
                "latency_delta": latency_delta,
                "cost_delta": cost_delta,
            }
        )


def test_ports_are_runtime_checkable():
    assert isinstance(_Armora(), IArmoraResiliencePort)
    assert isinstance(_Dipa(), IDipaResiliencePort)
    assert isinstance(_Experience(), IExperienceStorePort)
    assert isinstance(_Performix(), IPerformixResiliencePort)


def test_engine_uses_experience_and_performix_ports():
    exp = _Experience()
    perf = _Performix()
    engine = build_resilience_engine(
        catalog=make_catalog(),
        experience=exp,
        performix=perf,
    )
    engine.evaluate(
        make_plan(),
        make_signals(model_available=False, historical_failures=2),
    )
    assert exp.stored
    assert perf.samples


def test_dipa_patch_shape_compatible():
    dipa = _Dipa()
    engine = build_resilience_engine(catalog=make_catalog())
    decision = engine.evaluate(
        make_plan(),
        make_signals(model_available=False, historical_failures=2),
    )
    assert decision.alternative is not None
    patch = decision.alternative.to_plan_patch()
    dipa.apply_plan_patch("ex_test", patch)
    assert dipa.patches[0]["model"]
    assert "metadata" in dipa.patches[0]
