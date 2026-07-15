from __future__ import annotations

from .conftest import fresh_store, make_record


def test_events_emitted():
    store = fresh_store()
    seen: list[str] = []
    store.events.subscribe(lambda e: seen.append(e.type))
    store.record(make_record(execution_id="ev1"))
    store.compute_analytics()
    store.generate_dataset("analytics")
    store.exporter.export_dataset(store.generate_benchmark_dataset())
    store.archive("ev1")
    assert "ExecutionRecorded" in seen
    assert "AnalyticsUpdated" in seen
    assert "DatasetGenerated" in seen
    assert "ExecutionArchived" in seen

    hist = store.events.history(event_type="ExecutionRecorded")
    assert hist[0].to_otel_attributes()["nexus.swarm.experience.event"] == "ExecutionRecorded"
