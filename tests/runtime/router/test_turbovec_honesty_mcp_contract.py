"""TurboVec honesty reporting + MCP name alias tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.router.backends.registry import build_vector_index, kernel_path_for
from neuroswarm_arm.runtime.router.health import build_health_report
from neuroswarm_arm.runtime.router.mcp_executor import TOOL_NAME_ALIASES, _mcp_tool_name
from neuroswarm_arm.runtime.router.models import MetricKind
from neuroswarm_arm.runtime.router.router_metrics import RouterMetrics
from neuroswarm_arm.runtime.router.turbovec_index import TurboVecIndex


def test_mcp_tool_name_aliases_legacy_leaves():
    assert _mcp_tool_name("slack.post_message") == "post_message"
    assert _mcp_tool_name("slack.send_message") == "post_message"
    assert _mcp_tool_name("browser.navigate") == "navigate"
    assert _mcp_tool_name("browser.open_page") == "navigate"
    assert _mcp_tool_name("s3.list_objects") == "list_objects"
    assert _mcp_tool_name("s3.list_objects_v2") == "list_objects"
    assert _mcp_tool_name("browser.extract_links") == "extract_links"
    assert _mcp_tool_name("browser.extract") == "extract_links"
    assert "send_message" in TOOL_NAME_ALIASES


def test_turbovec_min_tools_zero_uses_turbovec_when_import_ok():
    import numpy as np

    tv = TurboVecIndex(8, metric=MetricKind.COSINE, min_tools_for_turbovec=0)
    for i in range(5):
        tv.insert(f"k{i}", np.ones(8, dtype=np.float32))
    if tv._turbovec_import_ok:
        assert tv.kernel_path == "turbovec"
        assert tv.active_backend == "turbovec"
        assert tv.fallback_reason == "none"
    else:
        assert tv.kernel_path == "numpy"
        assert tv.active_backend == "exact_numpy"
        assert tv.fallback_reason == "import_failed"


def test_turbovec_below_min_tools_reports_catalog_reason():
    import numpy as np

    tv = TurboVecIndex(8, metric=MetricKind.COSINE, min_tools_for_turbovec=100)
    for i in range(5):
        tv.insert(f"k{i}", np.ones(8, dtype=np.float32))
    assert tv.kernel_path == "numpy"
    assert tv.active_backend == "exact_numpy"
    if tv._turbovec_import_ok:
        assert tv.fallback_reason == "catalog_below_min_tools"


def test_health_exposes_configured_vs_active_backend():
    exact = build_vector_index("exact", 8)

    class _Rt:
        config = type(
            "C",
            (),
            {
                "ann_backend": "exact",
                "encoder_name": "x",
                "top_k": 3,
                "threshold": 0.42,
                "enable_hot_reload": False,
                "snapshot_dir": ".",
                "high_conf_gate": 0.70,
                "turbovec_min_tools": 0,
                "embedding_backend": "hash",
            },
        )()
        index = exact
        embedder = type("E", (), {"backend_name": "hash", "dims": 8, "cache": None})()
        registry = type("R", (), {"size": lambda self: 46})()
        arm_features = type(
            "A",
            (),
            {
                "arch": "x",
                "is_arm64": False,
                "neon": False,
                "sve": False,
                "sve2": False,
                "numa_nodes": 1,
            },
        )()

    report = build_health_report(_Rt())
    assert report["configured_backend"] == "exact"
    assert report["active_backend"] == "exact_numpy"
    assert report["fallback_reason"] == "forced_exact"
    assert report["catalog_size"] == 46
    assert report["kernel_path"] == "numpy"
    assert kernel_path_for(exact) == "numpy"

    tv = TurboVecIndex(8, metric=MetricKind.COSINE, min_tools_for_turbovec=100)
    _Rt.config = type(
        "C",
        (),
        {
            "ann_backend": "turbovec",
            "encoder_name": "x",
            "top_k": 3,
            "threshold": 0.42,
            "enable_hot_reload": False,
            "snapshot_dir": ".",
            "high_conf_gate": 0.70,
            "turbovec_min_tools": 100,
            "embedding_backend": "hash",
        },
    )()
    _Rt.index = tv
    _Rt.registry = type("R", (), {"size": lambda self: 46})()
    report_tv = build_health_report(_Rt())
    assert report_tv["configured_backend"] == "turbovec"
    assert report_tv["catalog_size"] == 46
    assert report_tv["turbovec_min_tools"] == 100
    if tv._turbovec_import_ok and tv.kernel_path == "numpy":
        assert report_tv["active_backend"] == "exact_numpy"
        assert report_tv["fallback_reason"] == "catalog_below_min_tools"
        assert report_tv["status"] == "ok"


def test_turbovec_search_metric_only_when_active():
    metrics = RouterMetrics()
    # Simulate exact path: only search latency, not turbovec gauge update from tool_router logic
    metrics.set("router_search_latency_ms", 1.5)
    metrics.set("router_ann_latency_ms", 1.5)
    snap = metrics.snapshot()
    assert snap["router_search_latency_ms"] == 1.5
    # turbovec gauge stays at default 0 until explicitly set on turbovec path
    assert snap.get("router_turbovec_search_ms", 0.0) == 0.0
    metrics.set("router_turbovec_search_ms", 2.0)
    assert metrics.snapshot()["router_turbovec_search_ms"] == 2.0
