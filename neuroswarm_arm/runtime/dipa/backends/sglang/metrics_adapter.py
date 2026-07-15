"""Scrape / adapt SGLang Prometheus text into DIPA local gauges."""

from __future__ import annotations

from typing import Any, Mapping


def parse_prometheus_text(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name, raw = parts[0], parts[1]
        # Strip labels: metric{...} value
        if "{" in name:
            name = name.split("{", 1)[0]
        try:
            out[name] = float(raw)
        except ValueError:
            continue
    return out


class SGLangMetricsAdapter:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client
        self._last: dict[str, float] = {}

    def scrape(self) -> Mapping[str, float]:
        if self.client is None:
            return dict(self._last)
        text = ""
        try:
            text = self.client.metrics_text()
        except Exception:
            return dict(self._last)
        parsed = parse_prometheus_text(text)
        self._last = parsed
        return dict(parsed)
