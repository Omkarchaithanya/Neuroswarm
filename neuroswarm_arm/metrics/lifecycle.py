"""RMF lifecycle — registry, buffer, collectors, exporters, optional scrape server."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from .aggregators import WindowAggregator
from .buffer import AsyncMetricBuffer
from .collectors import CollectorHub, NumaCollector, PerformixCollector, PsutilCollector
from .config import RMFRuntimeConfig, load_rmf_config
from .domains import register_all_domains
from .exporters.base import build_exporter
from .exporters.openmetrics import OpenMetricsExporter
from .exporters.prometheus import PrometheusExporter
from .metrics import MetricPublisher
from .plugins import discover_plugins, plugin_registry, _register_builtins
from .registry import MetricRegistry

logger = logging.getLogger(__name__)

_RMF: RuntimeMetricsFramework | None = None
_RMF_LOCK = threading.Lock()


class RuntimeMetricsFramework:
    """Production Runtime Metrics Framework control plane."""

    def __init__(self, config: RMFRuntimeConfig | None = None) -> None:
        self.config = config or load_rmf_config()
        self.registry = MetricRegistry(cardinality_max=self.config.cardinality_max)
        register_all_domains(self.registry)
        self.buffer = AsyncMetricBuffer(
            self.registry,
            max_size=self.config.buffer_max,
            flush_ms=self.config.flush_ms,
            flush_batch=self.config.flush_batch,
        )
        self.publisher = MetricPublisher(self.registry)
        self.aggregator = WindowAggregator(self.registry)
        self.collectors = CollectorHub()
        self._exporters: dict[str, Any] = {}
        self._extra_sources: list[Callable[[], str]] = []
        self._scrape_server: ThreadingHTTPServer | None = None
        self._scrape_thread: threading.Thread | None = None
        self._started = False

        if self.config.plugins:
            discover_plugins(self.config.plugins)
        _register_builtins()

        self.collectors.add(PsutilCollector(self.registry, interval_s=self.config.collector_interval_s))
        self.collectors.add(
            PerformixCollector(
                self.registry,
                path=self.config.performix_path,
                interval_s=self.config.collector_interval_s,
                enabled=self.config.performix_enabled,
            )
        )
        self.collectors.add(
            NumaCollector(self.registry, interval_s=max(15.0, self.config.collector_interval_s))
        )

        for name in self.config.exporters:
            try:
                kwargs: dict[str, Any] = {}
                if name == "otlp":
                    kwargs["endpoint"] = self.config.otlp_endpoint
                    kwargs["insecure"] = self.config.otlp_insecure
                self._exporters[name] = build_exporter(name, self.registry, **kwargs)
            except Exception as exc:
                logger.warning("failed to build exporter %s: %s", name, exc)

        if "prometheus" not in self._exporters:
            self._exporters["prometheus"] = PrometheusExporter(self.registry)

    def start(self) -> None:
        if not self.config.enabled or self._started:
            return
        self.config.work_dir.mkdir(parents=True, exist_ok=True)
        self.buffer.start()
        self.collectors.start()
        if self.config.standalone_scrape and self.config.scrape_port > 0:
            self._start_scrape_server()
        self._started = True

    def shutdown(self, *, timeout: float = 2.0) -> None:
        self.collectors.stop()
        self.buffer.stop(timeout=timeout)
        self._stop_scrape_server()
        self._started = False

    def register_source(self, source: Callable[[], str]) -> None:
        self._extra_sources.append(source)

    def inc(self, name: str, value: float = 1.0, *, labels: dict[str, str] | None = None) -> None:
        self.registry.inc(name, value, labels=labels)

    def set(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        self.registry.set(name, value, labels=labels)

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        self.registry.observe(name, value, labels=labels)
        self.aggregator.observe(name, value, labels=labels)

    def export_prometheus(self) -> str:
        self.buffer.flush()
        exporter = self._exporters.get("prometheus") or PrometheusExporter(self.registry)
        text = exporter.export()
        extras = []
        for src in self._extra_sources:
            try:
                chunk = src()
                if chunk:
                    extras.append(chunk if chunk.endswith("\n") else chunk + "\n")
            except Exception as exc:
                logger.debug("extra metric source failed: %s", exc)
        return text + "".join(extras)

    def export_openmetrics(self) -> str:
        self.buffer.flush()
        exporter = self._exporters.get("openmetrics") or OpenMetricsExporter(self.registry)
        return exporter.export()

    def export(self, fmt: str = "prometheus") -> tuple[str, str]:
        if fmt == "openmetrics":
            return self.export_openmetrics(), OpenMetricsExporter(self.registry).content_type()
        text = self.export_prometheus()
        exporter = self._exporters.get("prometheus") or PrometheusExporter(self.registry)
        return text, exporter.content_type()

    def check_auth(self, authorization: str | None) -> bool:
        token = self.config.metrics_token
        if not token:
            return True
        if not authorization:
            return False
        if authorization.startswith("Bearer "):
            return authorization.removeprefix("Bearer ").strip() == token
        return authorization.strip() == token

    def _start_scrape_server(self) -> None:
        framework = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path not in {"/metrics", "/"}:
                    self.send_response(404)
                    self.end_headers()
                    return
                if not framework.check_auth(self.headers.get("Authorization")):
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"unauthorized\n")
                    return
                accept = self.headers.get("Accept", "")
                fmt = "openmetrics" if "openmetrics" in accept else "prometheus"
                body, ctype = framework.export(fmt)
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        server = ThreadingHTTPServer((self.config.scrape_host, self.config.scrape_port), Handler)
        self._scrape_server = server
        self._scrape_thread = threading.Thread(target=server.serve_forever, name="rmf-scrape", daemon=True)
        self._scrape_thread.start()
        logger.info("RMF scrape server on %s:%s", self.config.scrape_host, self.config.scrape_port)

    def _stop_scrape_server(self) -> None:
        if self._scrape_server is not None:
            self._scrape_server.shutdown()
            self._scrape_server.server_close()
            self._scrape_server = None
        if self._scrape_thread is not None:
            self._scrape_thread.join(timeout=2.0)
            self._scrape_thread = None


def build_rmf(config: RMFRuntimeConfig | None = None, *, start: bool = True) -> RuntimeMetricsFramework:
    global _RMF
    with _RMF_LOCK:
        framework = RuntimeMetricsFramework(config)
        if start and framework.config.enabled:
            framework.start()
        _RMF = framework
        return framework


def get_rmf() -> RuntimeMetricsFramework:
    global _RMF
    if _RMF is None:
        return build_rmf()
    return _RMF


def peek_rmf() -> RuntimeMetricsFramework | None:
    return _RMF


def get_registry() -> MetricRegistry:
    return get_rmf().registry
