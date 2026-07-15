"""Multi-criteria backend selection over the registry."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from ..interfaces.types import (
    ExecutionPlan,
    HealthState,
    HealthStatus,
    InferenceRequest,
    RouteScore,
)


class _BackendLike(Protocol):
    name: str

    @property
    def capabilities(self) -> Any: ...


class _RegistryLike(Protocol):
    def list(self) -> list[str]: ...

    def get(self, name: str) -> _BackendLike: ...


class BackendSelector:
    """Score backends by health, utilization, priority, streaming, and warm."""

    def __init__(
        self,
        registry: _RegistryLike,
        routing_cfg: Mapping[str, Any] | None = None,
        priorities: Mapping[str, float] | None = None,
        *,
        warm_checker: Callable[[str], bool] | None = None,
    ) -> None:
        self.registry = registry
        cfg = dict(routing_cfg or {})
        self._weights: dict[str, float] = {
            str(k): float(v) for k, v in (cfg.get("weights") or {}).items()
        }
        yaml_pri = {
            str(k): float(v) for k, v in (cfg.get("backend_priorities") or {}).items()
        }
        self._priorities: dict[str, float] = {**yaml_pri, **dict(priorities or {})}
        self._warm_checker = warm_checker
        self._health_cache: dict[str, HealthStatus] = {}

    def update_health(self, snapshot: Mapping[str, HealthStatus]) -> None:
        self._health_cache = {str(k): v for k, v in snapshot.items()}

    def select(self, req: InferenceRequest, plan: ExecutionPlan) -> str:
        names = list(self.registry.list())
        if not names:
            plan.backend = plan.backend or "mock"
            plan.scores["backend"] = 0.0
            return plan.backend

        scored = [self._score(name, req, plan) for name in names]
        scored.sort(key=lambda s: s.score, reverse=True)
        best = scored[0]
        plan.backend = best.name
        plan.scores["backend"] = best.score
        for key, val in best.factors.items():
            plan.scores[f"backend_{key}"] = val
        plan.metadata.setdefault("backend_route", {})
        plan.metadata["backend_route"] = {
            "name": best.name,
            "score": best.score,
            "factors": dict(best.factors),
            "ranked": [{"name": s.name, "score": s.score} for s in scored[:5]],
        }
        return best.name

    def _score(
        self, name: str, req: InferenceRequest, plan: ExecutionPlan
    ) -> RouteScore:
        w = self._weights
        factors: dict[str, float] = {}

        health = self._health_cache.get(name)
        if health is None:
            health = self._peek_health(name)

        state = health.state if health else HealthState.UNKNOWN
        if state == HealthState.HEALTHY:
            factors["health"] = 1.0
        elif state == HealthState.DEGRADED:
            factors["health"] = 0.45
        elif state == HealthState.UNHEALTHY:
            factors["health"] = 0.05
        else:
            factors["health"] = 0.5

        util = float(health.utilization) if health else 0.0
        factors["utilization"] = max(0.0, 1.0 - min(1.0, util))

        priority = float(self._priorities.get(name, 0.5))
        factors["priority"] = min(1.0, max(0.0, priority))

        needs_stream = bool(req.stream or plan.stream)
        caps = self._capabilities(name)
        if needs_stream:
            factors["streaming"] = 1.0 if getattr(caps, "streaming", True) else 0.1
        else:
            factors["streaming"] = 0.7

        warm = False
        if self._warm_checker is not None:
            try:
                warm = bool(self._warm_checker(plan.model))
            except Exception:  # noqa: BLE001 — warm is advisory
                warm = False
        factors["warm_hit"] = 1.0 if warm else 0.4

        score = (
            factors["health"] * w.get("health", 0.15)
            + factors["utilization"] * w.get("utilization", 0.10)
            + factors["priority"] * 0.25
            + factors["streaming"] * w.get("streaming", 0.05)
            + factors["warm_hit"] * w.get("warm_hit", 0.10)
        )
        return RouteScore(name=name, score=score, factors=factors)

    def _capabilities(self, name: str) -> Any:
        try:
            backend = self.registry.get(name)
            return getattr(backend, "capabilities", None)
        except Exception:  # noqa: BLE001
            return None

    def _peek_health(self, name: str) -> HealthStatus | None:
        try:
            backend = self.registry.get(name)
        except Exception:  # noqa: BLE001
            return None
        cached = getattr(backend, "last_health", None)
        if isinstance(cached, HealthStatus):
            return cached
        # Sync health hook if a backend exposes one.
        sync_health = getattr(backend, "health_sync", None)
        if callable(sync_health):
            try:
                result = sync_health()
                if isinstance(result, HealthStatus):
                    return result
            except Exception:  # noqa: BLE001
                return HealthStatus(state=HealthState.UNKNOWN)
        return None
