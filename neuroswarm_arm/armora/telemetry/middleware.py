"""FastAPI / Starlette ASGI middleware — root request span + context."""

from __future__ import annotations

import time
from typing import Any, Callable
from uuid import uuid4

from .context import RuntimeTraceContext, reset_current_context, set_current_context
from .schemas import AttributeKeys, EventType, SpanNames


class ROFMiddleware:
    """ASGI middleware that binds RuntimeTraceContext for each HTTP request."""

    def __init__(self, app: Any, rof: Any) -> None:
        self.app = app
        self.rof = rof

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        request_id = headers.get("x-request-id") or uuid4().hex
        agent_id = headers.get("x-agent-id", "")
        path = scope.get("path", "")
        method = scope.get("method", "GET")

        if not self.rof.config.enabled:
            await self.app(scope, receive, send)
            return

        ctx = RuntimeTraceContext(request_id=request_id, agent_id=agent_id)
        token = set_current_context(ctx)
        t0 = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 200))
            await send(message)

        try:
            with self.rof.span(
                SpanNames.REQUEST,
                attributes={
                    "http.method": method,
                    "http.route": path,
                    AttributeKeys.REQUEST_ID: request_id,
                },
            ):
                self.rof.emit_builtin(
                    EventType.ADMISSION_STARTED,
                    payload={"path": path, "method": method},
                )
                await self.app(scope, receive, send_wrapper)
                self.rof.emit_builtin(
                    EventType.ADMISSION_FINISHED,
                    payload={"path": path, "status": status_code},
                )
        except Exception as exc:
            self.rof.counter("nexus_requests_total", 1.0, labels={"outcome": "error"})
            self.rof.log("ERROR", "request failed", error=str(exc), path=path)
            raise
        finally:
            latency = time.perf_counter() - t0
            self.rof.histogram("nexus_request_latency_seconds", latency)
            outcome = "ok" if status_code < 500 else "error"
            self.rof.counter("nexus_requests_total", 1.0, labels={"outcome": outcome})
            reset_current_context(token)


def install_rof_middleware(app: Any, rof: Any) -> None:
    """Install ROF middleware on a Starlette/FastAPI app."""
    app.add_middleware(ROFMiddleware, rof=rof)
