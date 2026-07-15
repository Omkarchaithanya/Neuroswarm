"""OpenTelemetry adapter for DIPA — thin facade over TelemetryExporter."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from neuroswarm_arm.runtime.dipa.control.telemetry_exporter import TelemetryExporter


class OpenTelemetryAdapter:
    """Backward-compatible span API; prefers shared TelemetryExporter."""

    def __init__(
        self,
        enabled: bool = False,
        endpoint: str = "",
        *,
        exporter: TelemetryExporter | None = None,
        service_name: str = "nexus-arm-dipa",
    ) -> None:
        self.exporter = exporter or TelemetryExporter(
            enabled=enabled, endpoint=endpoint, service_name=service_name
        )
        self.enabled = self.exporter.enabled
        self.endpoint = endpoint

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Any]:
        with self.exporter.span(name, **attrs) as sp:
            yield sp
