"""Metric registry unit tests."""

from __future__ import annotations

from neuroswarm_arm.metrics.config import RMFRuntimeConfig
from neuroswarm_arm.metrics.domains import register_all_domains
from neuroswarm_arm.metrics.lifecycle import RuntimeMetricsFramework
from neuroswarm_arm.metrics.registry import MetricRegistry
from neuroswarm_arm.metrics.schemas import MetricDef, MetricDomain, MetricType


def test_register_and_counter() -> None:
    reg = MetricRegistry()
    reg.register(
        MetricDef(
            name="nexus_request_total",
            metric_type=MetricType.COUNTER,
            help="requests",
            domain=MetricDomain.REQUEST,
            label_keys=("status",),
        )
    )
    reg.inc("nexus_request_total", 2.0, labels={"status": "ok"})
    snap = reg.snapshot()
    assert any(s.name == "nexus_request_total" and s.value == 2.0 for s in snap.series)


def test_forbidden_labels_dropped() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    reg.inc(
        "nexus_request_total",
        1.0,
        labels={"status": "ok", "request_id": "secret", "request_type": "http", "streaming": "false", "reasoning": "false", "agent_type": "t"},
    )
    text_labels = " ".join(str(s.labels) for s in reg.snapshot().series if s.name == "nexus_request_total")
    assert "request_id" not in text_labels
    assert reg.policy.dropped_labels >= 1


def test_cardinality_cap() -> None:
    reg = MetricRegistry(cardinality_max=3)
    reg.register(
        MetricDef(
            name="nexus_test_card_total",
            metric_type=MetricType.COUNTER,
            help="card",
            domain=MetricDomain.RMF,
            label_keys=("status",),
        )
    )
    for i in range(10):
        reg.inc("nexus_test_card_total", 1.0, labels={"status": f"s{i}"})
    series = [s for s in reg.snapshot().series if s.name == "nexus_test_card_total"]
    assert len(series) <= 3
    assert reg.policy.cardinality_rejects >= 1


def test_histogram_buckets() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    reg.observe("nexus_request_duration_seconds", 0.2, labels={"status": "ok", "request_type": "http", "streaming": "false", "reasoning": "false", "agent_type": "g"})
    series = [s for s in reg.snapshot().series if s.name == "nexus_request_duration_seconds"]
    assert series
    assert series[0].count == 1.0
    assert series[0].sum == 0.2
    assert series[0].bucket_counts


def test_alias_resolution() -> None:
    reg = MetricRegistry()
    register_all_domains(reg)
    reg.inc("neuroswarm_requests_total", 1.0, labels={"status": "ok", "request_type": "http", "streaming": "false", "reasoning": "false", "agent_type": "g"})
    assert reg.resolve_name("neuroswarm_requests_total") == "nexus_request_total"


def test_build_rmf_export() -> None:
    cfg = RMFRuntimeConfig(enabled=True, exporters=("prometheus", "openmetrics"), performix_enabled=False)
    rmf = RuntimeMetricsFramework(cfg)
    rmf.start()
    try:
        rmf.inc("nexus_request_total", 1.0, labels={"status": "ok", "request_type": "http", "streaming": "false", "reasoning": "false", "agent_type": "g"})
        text = rmf.export_prometheus()
        assert "nexus_request_total" in text
        om = rmf.export_openmetrics()
        assert "# EOF" in om
    finally:
        rmf.shutdown()
