"""Exporter tests."""

from __future__ import annotations

from neuroswarm_arm.metrics.exporters.openmetrics import OpenMetricsExporter
from neuroswarm_arm.metrics.exporters.otlp import OTLPMetricsExporter
from neuroswarm_arm.metrics.exporters.prometheus import PrometheusExporter
from neuroswarm_arm.metrics.domains import register_all_domains
from neuroswarm_arm.metrics.registry import MetricRegistry


def _reg() -> MetricRegistry:
    reg = MetricRegistry()
    register_all_domains(reg)
    reg.inc(
        "nexus_request_total",
        3.0,
        labels={
            "status": "ok",
            "request_type": "http",
            "streaming": "false",
            "reasoning": "false",
            "agent_type": "gateway",
        },
    )
    reg.observe(
        "nexus_request_duration_seconds",
        0.05,
        labels={
            "status": "ok",
            "request_type": "http",
            "streaming": "false",
            "reasoning": "false",
            "agent_type": "gateway",
        },
    )
    return reg


def test_prometheus_exporter_text() -> None:
    text = PrometheusExporter(_reg()).export()
    assert "# TYPE nexus_request_total counter" in text
    assert "nexus_request_total{" in text or "nexus_request_total " in text
    assert "nexus_request_duration_seconds_bucket" in text


def test_openmetrics_eof() -> None:
    text = OpenMetricsExporter(_reg()).export()
    assert text.strip().endswith("# EOF")
    assert "application/openmetrics" in OpenMetricsExporter(_reg()).content_type()


def test_otlp_exporter_fallback_text() -> None:
    exp = OTLPMetricsExporter(_reg(), endpoint="")
    text = exp.export()
    assert "nexus_request_total" in text
