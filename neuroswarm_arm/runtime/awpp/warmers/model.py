"""Model warmer — best-effort HTTP health / warmup against tier endpoints."""

from __future__ import annotations

import time
from typing import Any, Mapping

from neuroswarm_arm.runtime.awpp.interfaces import IWarmer, WarmResult


class ModelWarmer(IWarmer):
    """Touch llama.cpp (or compatible) tier endpoints so pages stay resident.

    Honesty: many backends only expose ``/health``; that is a soft warm, not a
    guarantee of weight residency on Axion CPU.
    """

    kind = "model"

    def __init__(
        self,
        urls: Mapping[str, str] | None = None,
        *,
        timeout_s: float = 2.0,
        http_client: Any | None = None,
    ) -> None:
        self.urls = {str(k): str(v).rstrip("/") for k, v in dict(urls or {}).items()}
        self.timeout_s = timeout_s
        self._http = http_client
        self._warm: set[str] = set()

    def _resolve_url(self, key: str) -> str | None:
        if key in self.urls:
            return self.urls[key]
        # Accept bare tier names / model aliases
        lowered = key.lower()
        for name, url in self.urls.items():
            if name.lower() in lowered or lowered in name.lower():
                return url
        if key.startswith("http://") or key.startswith("https://"):
            return key.rstrip("/")
        return None

    async def warm(self, key: str, *, metadata: Mapping[str, Any] | None = None) -> WarmResult:
        t0 = time.perf_counter()
        url = self._resolve_url(key)
        if not url:
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=False,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error="unknown_model_url",
            )
        meta = dict(metadata or {})
        path = str(meta.get("warmup_path") or "/health")
        try:
            if self._http is not None:
                resp = await self._http.get(f"{url}{path}", timeout=self.timeout_s)
                ok = int(getattr(resp, "status_code", 500)) < 400
            else:
                import httpx

                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    resp = await client.get(f"{url}{path}")
                    ok = resp.status_code < 400
                    # Optional POST /warmup when advertised
                    if ok and meta.get("try_warmup_post"):
                        try:
                            await client.post(f"{url}/warmup", json={"model": key})
                        except Exception:
                            pass
            if ok:
                self._warm.add(key)
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=ok,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                metadata={"url": url, "path": path},
            )
        except Exception as exc:  # noqa: BLE001
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=False,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )

    def is_warm(self, key: str) -> bool:
        return key in self._warm
