"""Alert and recording rule generation tests."""

from __future__ import annotations

from neuroswarm_arm.metrics.alerts import default_alert_groups, render_alert_yaml, write_alert_rules
from neuroswarm_arm.metrics.dashboards import default_dashboards, write_dashboards
from neuroswarm_arm.metrics.recording_rules import (
    default_recording_groups,
    render_recording_yaml,
    write_recording_rules,
)


def test_alert_yaml_contains_core_alerts() -> None:
    text = render_alert_yaml()
    assert "NexusHighLatency" in text
    assert "NexusBudgetExhaustion" in text
    assert "NexusCPUSaturation" in text
    assert len(default_alert_groups()[0].rules) >= 10


def test_recording_yaml() -> None:
    text = render_recording_yaml()
    assert "nexus:request_duration_seconds:p95_5m" in text
    assert "nexus:planner_accuracy:avg5m" in text
    assert default_recording_groups()


def test_write_artifacts() -> None:
    from pathlib import Path
    import uuid

    base = Path(__file__).resolve().parents[2] / "work" / "rmf-pytest" / uuid.uuid4().hex
    base.mkdir(parents=True, exist_ok=True)
    alerts = write_alert_rules(base / "alerts.yml")
    rec = write_recording_rules(base / "recording.yml")
    boards = write_dashboards(base / "dashboards")
    assert alerts.exists() and rec.exists()
    assert len(boards) == 14
    assert len(default_dashboards()) == 14
