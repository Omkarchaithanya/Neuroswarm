"""MetricsStore compatibility facade tests."""

from __future__ import annotations

from neuroswarm_arm.metrics.compat import MetricsStore, build_default_store
from neuroswarm_arm.metrics.config import RMFRuntimeConfig
from neuroswarm_arm.metrics.lifecycle import RuntimeMetricsFramework


def test_metrics_store_local_export() -> None:
    store = MetricsStore()
    store.describe("demo_total", "counter", "demo")
    store.inc("demo_total", 2.0)
    text = store.export_prometheus()
    assert "demo_total 2.0" in text or "demo_total 2" in text


def test_dual_write_into_rmf() -> None:
    cfg = RMFRuntimeConfig(enabled=True, exporters=("prometheus",), performix_enabled=False)
    rmf = RuntimeMetricsFramework(cfg)
    rmf.start()
    try:
        store = build_default_store()
        store.bind(rmf)
        store.inc("neuroswarm_requests_total", 1.0)
        # dual-write uses legacy name; alias maps into nexus_request_total when registered
        text = rmf.export_prometheus()
        assert "neuroswarm_requests_total" in text or "nexus_request_total" in text
    finally:
        rmf.shutdown()
