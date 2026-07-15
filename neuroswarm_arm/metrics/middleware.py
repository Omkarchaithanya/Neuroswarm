"""FastAPI / ASGI middleware for RED request metrics."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .lifecycle import RuntimeMetricsFramework


class RMFMiddleware:
    """ASGI middleware publishing request RED metrics into RMF."""

    def __init__(self, app: Any, rmf: RuntimeMetricsFramework | None = None) -> None:
        self.app = app
        self._rmf = rmf

    @property
    def rmf(self) -> RuntimeMetricsFramework:
        if self._rmf is not None:
            return self._rmf
        from .lifecycle import get_rmf

        return get_rmf()

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in {"/metrics", "/health", "/ready"}:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500
        streaming = "false"
        self.rmf.inc("nexus_request_active", 1.0)

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code, streaming
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = {
                    k.decode().lower() if isinstance(k, bytes) else str(k).lower(): (
                        v.decode() if isinstance(v, bytes) else str(v)
                    )
                    for k, v in message.get("headers", [])
                }
                ctype = headers.get("content-type", "")
                if "text/event-stream" in ctype or "stream" in ctype:
                    streaming = "true"
            await send(message)

        error = False
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            error = True
            raise
        finally:
            elapsed = time.perf_counter() - start
            status = "error" if error or status_code >= 500 else "ok"
            labels = {
                "request_type": "http",
                "streaming": streaming,
                "reasoning": "false",
                "status": status,
                "agent_type": "gateway",
            }
            self.rmf.inc("nexus_request_active", -1.0)
            self.rmf.inc("nexus_request_total", 1.0, labels=labels)
            if status == "error":
                self.rmf.inc("nexus_request_failed_total", 1.0, labels=labels)
            else:
                self.rmf.inc("nexus_request_completed_total", 1.0, labels=labels)
            if streaming == "true":
                self.rmf.inc("nexus_request_streaming_total", 1.0, labels=labels)
            self.rmf.observe("nexus_request_duration_seconds", elapsed, labels=labels)


def install_rmf_middleware(app: Any, rmf: RuntimeMetricsFramework | None = None) -> None:
    app.add_middleware(RMFMiddleware, rmf=rmf)
