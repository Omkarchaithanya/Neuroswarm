from neuroswarm_arm.evolution.observation.otel_provider import (
    PrometheusObservationProvider,
    _arop_metric_name,
)


def test_arop_metric_name_strips_labels() -> None:
    assert _arop_metric_name('nexus_performix_hotspot_pct{function="ggml_compute"}') == (
        "nexus_performix_hotspot_pct"
    )


def test_prometheus_text_skips_labeled_keys() -> None:
    prom = PrometheusObservationProvider(scrape_fn=lambda: {})
    text = prom.prometheus_text(
        {
            "nexus_performix_ipc": 2.5,
            'nexus_performix_hotspot_pct{function="ggml_compute"}': 18.2,
            'nexus_performix_hotspot_pct{function="llama_decode"}': 42.5,
        }
    )
    assert 'arop_metric{name="nexus_performix_ipc"} 2.5' in text
    assert "ggml_compute" not in text
    assert "function=" not in text
    # Must remain parseable: no nested quotes inside name=
    assert 'name="nexus_performix_hotspot_pct{function=' not in text
