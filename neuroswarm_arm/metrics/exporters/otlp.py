"""OTLP metrics exporter via OpenTelemetry MeterProvider."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..schemas import MetricType

if TYPE_CHECKING:
    from ..registry import MetricRegistry

logger = logging.getLogger(__name__)


class OTLPMetricsExporter:
    """Push registry gauges/counters to OTLP when endpoint configured."""

    def __init__(
        self,
        registry: MetricRegistry,
        *,
        endpoint: str = "",
        insecure: bool = True,
        **_kwargs: object,
    ) -> None:
        self.registry = registry
        self.endpoint = endpoint
        self.insecure = insecure
        self._meter: Any = None
        self._instruments: dict[str, Any] = {}
        self._last_export = ""
        if endpoint:
            self._init_otel(endpoint, insecure)

    def _init_otel(self, endpoint: str, insecure: bool) -> None:
        try:
            from opentelemetry import metrics as otel_metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource

            try:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                    OTLPMetricExporter,
                )

                exporter = OTLPMetricExporter(endpoint=endpoint, insecure=insecure)
            except Exception:
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                    OTLPMetricExporter as HTTPExporter,
                )

                exporter = HTTPExporter(endpoint=endpoint)

            reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10000)
            provider = MeterProvider(
                resource=Resource.create({"service.name": "nexus-arm-rmf"}),
                metric_readers=[reader],
            )
            otel_metrics.set_meter_provider(provider)
            self._meter = otel_metrics.get_meter("nexus.arm.rmf")
        except Exception as exc:
            logger.warning("OTLP metrics init failed: %s", exc)
            self._meter = None

    def content_type(self) -> str:
        return "application/json"

    def export(self) -> str:
        snap = self.registry.snapshot()
        if self._meter is not None:
            for item in snap.series:
                try:
                    self._mirror(item)
                except Exception:
                    continue
        # Return prometheus-compatible text for scrape merge convenience
        from .prometheus import PrometheusExporter

        text = PrometheusExporter(self.registry).export()
        self._last_export = text
        return text

    def _mirror(self, item: Any) -> None:
        name = item.name.replace(".", "_")
        attrs = dict(item.labels)
        if item.metric_type == MetricType.COUNTER:
            counter = self._instruments.get(name)
            if counter is None:
                counter = self._meter.create_counter(name, description=item.help)
                self._instruments[name] = counter
            # OTel counters are delta; we set absolute via gauge mirror instead
            gauge_name = f"{name}_abs"
            gauge = self._instruments.get(gauge_name)
            if gauge is None:
                gauge = self._meter.create_observable_gauge(
                    gauge_name,
                    callbacks=[lambda _o, n=name, v=item.value, a=attrs: _obs(v, a)],
                )
                self._instruments[gauge_name] = gauge
        else:
            gauge_name = name
            if gauge_name not in self._instruments:
                value = item.value if item.metric_type not in (MetricType.HISTOGRAM, MetricType.SUMMARY) else item.sum
                attrs_local = attrs

                def _cb(options: Any, v: float = value, a: dict[str, str] = attrs_local) -> Any:
                    from opentelemetry.metrics import Observation

                    return [Observation(v, a)]

                self._instruments[gauge_name] = self._meter.create_observable_gauge(
                    gauge_name,
                    callbacks=[_cb],
                    description=item.help,
                )


def _obs(value: float, attrs: dict[str, str]) -> Any:
    from opentelemetry.metrics import Observation

    return [Observation(value, attrs)]
