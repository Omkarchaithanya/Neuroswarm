"""AWPP heuristic warm connector — fallback when predictive path skips/fails."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..interfaces.types import ExecutionPlan, InferenceRequest
from ..interfaces.warm import IWarmConnector


class SupportsMAKSPrefetch(Protocol):
    async def prefetch(self, req: Any) -> Any: ...

    async def warm(self, kv_id: str) -> None: ...


class HeuristicWarmConnector(IWarmConnector):
    """Async warm-up surface. Optionally prefetches KV via MAKS."""

    def __init__(self, maks: SupportsMAKSPrefetch | None = None) -> None:
        self._warm: set[str] = set()
        self._pending: set[str] = set()
        self._maks = maks

    def bind_maks(self, maks: SupportsMAKSPrefetch) -> None:
        self._maks = maks

    async def ensure_warm(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        *,
        hints: Mapping[str, Any] | None = None,
    ) -> bool:
        model = plan.model or req.model
        if model in self._warm:
            return True
        await self.prefetch(model, req.session_id)
        self._warm.add(model)
        return True

    async def prefetch(self, model: str, session_id: str = "") -> None:
        self._pending.discard(model)
        if self._maks is not None:
            try:
                from neuroswarm_arm.runtime.maks.models import KVIdentity, PrefetchRequest

                await self._maks.prefetch(
                    PrefetchRequest(
                        session_id=session_id,
                        identity=KVIdentity(model_id=model),
                        pin=False,
                    )
                )
            except Exception:
                pass
        self._warm.add(model)

    def is_warm(self, model: str) -> bool:
        return model in self._warm
