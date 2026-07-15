"""WarmupManager — pre-warm backends / models / prefixes before admit."""

from __future__ import annotations

import time
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.interfaces.warm import IWarmConnector

from .backend_manager import BackendManager
from .model_manager import ModelManager


class WarmupManager:
    def __init__(
        self,
        backends: BackendManager,
        models: ModelManager,
        warm: IWarmConnector | None = None,
        prefix_cache: Any | None = None,
    ) -> None:
        self.backends = backends
        self.models = models
        self.warm = warm
        self.prefix_cache = prefix_cache
        self._last: dict[str, Any] = {}

    def warmup(self, *, model: str | None = None) -> Mapping[str, Any]:
        t0 = time.perf_counter()
        results: dict[str, Any] = {"backends": {}, "model": model}
        for name in self.backends.list():
            be = self.backends.get(name)
            if be is None:
                continue
            warm_fn = getattr(be, "warmup", None)
            try:
                if callable(warm_fn):
                    warm_fn(model=model)
                    results["backends"][name] = "ok"
                else:
                    import asyncio

                    status = asyncio.run(be.health())
                    results["backends"][name] = status.state.value
            except Exception as exc:
                results["backends"][name] = f"error:{exc}"
        if self.warm is not None and model:
            try:
                intent = getattr(self.warm, "predict", None)
                if callable(intent):
                    intent(model)
                results["awpp"] = "ok"
            except Exception as exc:
                results["awpp"] = f"error:{exc}"
        results["latency_ms"] = (time.perf_counter() - t0) * 1000.0
        results["models"] = self.models.snapshot()
        self._last = results
        return results

    def warmup_prefix(self, prefix_text: str, *, session_id: str = "") -> Mapping[str, Any]:
        if self.prefix_cache is None:
            return {"ok": False, "skipped": True}
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.prefix_cache.warm(prefix_text, session_id=session_id)
            )
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(
                    self.prefix_cache.warm(prefix_text, session_id=session_id)
                )
            ).result()

    def last(self) -> Mapping[str, Any]:
        return dict(self._last)
