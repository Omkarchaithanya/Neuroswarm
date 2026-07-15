"""ASGI middleware RED metrics test."""

from __future__ import annotations

import asyncio

from neuroswarm_arm.metrics.config import RMFRuntimeConfig
from neuroswarm_arm.metrics.lifecycle import RuntimeMetricsFramework
from neuroswarm_arm.metrics.middleware import RMFMiddleware


async def _app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": b"{}"})


def test_middleware_increments_request_total() -> None:
    cfg = RMFRuntimeConfig(enabled=True, exporters=("prometheus",), performix_enabled=False)
    rmf = RuntimeMetricsFramework(cfg)
    mw = RMFMiddleware(_app, rmf=rmf)

    async def _run() -> None:
        scope = {"type": "http", "path": "/v1/chat/completions", "method": "POST", "headers": []}
        await mw(scope, lambda: None, lambda m: asyncio.sleep(0))

    # Proper ASGI send/receive
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(mw({"type": "http", "path": "/v1/chat/completions", "method": "POST", "headers": []}, receive, send))
    text = rmf.export_prometheus()
    assert "nexus_request_total" in text
    assert "nexus_request_completed_total" in text
    assert len(messages) >= 2
