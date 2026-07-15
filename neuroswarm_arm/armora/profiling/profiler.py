"""Runtime Profiling Framework facade + DI factory."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .collector import ProfileCollector
from .config import RPFRuntimeConfig, load_rpf_config
from .connectors import PhaseSignalConnector, ProfileSignalBus, map_profile_to_runtime_signals
from .exporters import ProfileStore
from .feedback import ProfilerFeedbackService
from .lifecycle import LifecyclePhase, ProfilingLifecycle
from .plugins import RPFPluginRegistry
from .registry import ProfilerRegistry
from .schemas import (
    MetricBatch,
    ProfileSessionContext,
    ProfilingMode,
    ProviderCapabilities,
    RuntimeProfile,
    TelemetryMetadata,
)
from .traces import TraceRecorder

logger = logging.getLogger(__name__)


@dataclass
class RuntimeProfilingFramework:
    """ARMORA-owned RPF — observe → sample → RuntimeProfile → export → feedback."""

    config: RPFRuntimeConfig
    provider: Any
    collector: ProfileCollector
    telemetry: Any
    exporter: Any
    store: ProfileStore
    feedback: ProfilerFeedbackService
    registry: ProfilerRegistry
    plugins: RPFPluginRegistry
    lifecycle: ProfilingLifecycle
    signal_bus: ProfileSignalBus
    connector: PhaseSignalConnector
    traces: TraceRecorder
    _capabilities: dict[str, ProviderCapabilities] = field(default_factory=dict)

    def open_session(self, **kwargs: Any) -> ProfileSessionContext:
        try:
            self.lifecycle.transition(LifecyclePhase.COLLECTING)
            ctx = self.collector.open_session(**kwargs)
            self.signal_bus.set_active_session(ctx.session_id)
            return ctx
        except Exception as exc:
            logger.warning("rpf open_session failed: %s", exc)
            self.telemetry.record_failure(
                getattr(self.provider, "name", "unknown"), str(exc)
            )
            return ProfileSessionContext(mode=ProfilingMode.DISABLED, sampling_hz=0.0)

    def record_phase(self, session_id: str, **timings: Any) -> None:
        try:
            self.collector.record_phase(session_id, **timings)
        except Exception as exc:
            logger.warning("rpf record_phase failed: %s", exc)

    def sample(self, session_id: str) -> MetricBatch:
        try:
            return self.collector.sample(session_id)
        except Exception as exc:
            logger.warning("rpf sample failed: %s", exc)
            return MetricBatch(samples=[], provider="error", session_id=session_id)

    async def finalize(self, session_id: str) -> RuntimeProfile:
        return self.finalize_sync(session_id)

    def finalize_sync(self, session_id: str) -> RuntimeProfile:
        try:
            profile = self.collector.finalize(session_id)
            try:
                self.telemetry.record_profile(profile)
            except Exception as exc:
                logger.warning("rpf telemetry failed: %s", exc)
            try:
                self.store.write(profile)
            except Exception as exc:
                logger.warning("rpf store write failed: %s", exc)
            try:
                self.lifecycle.transition(LifecyclePhase.EXPORTING)
                self.exporter.export(profile)
            except Exception as exc:
                logger.warning("rpf export failed: %s", exc)
                try:
                    self.telemetry.record_failure(profile.profiler_used, str(exc))
                except Exception:
                    pass
            return profile
        except Exception as exc:
            logger.warning("rpf finalize failed: %s", exc)
            try:
                self.telemetry.record_failure(
                    getattr(self.provider, "name", "unknown"), str(exc)
                )
            except Exception:
                pass
            return RuntimeProfile(
                profiler_used="error",
                warnings=[str(exc)],
                mode=ProfilingMode.DISABLED,
            )

    def export_prometheus(self) -> str:
        try:
            return self.telemetry.export_prometheus()
        except Exception as exc:
            logger.warning("rpf prometheus export failed: %s", exc)
            return ""

    def snapshot(self) -> Mapping[str, Any]:
        try:
            return self.telemetry.snapshot()
        except Exception:
            return {}

    def capabilities(self) -> dict[str, ProviderCapabilities]:
        if self._capabilities:
            return dict(self._capabilities)
        try:
            self._capabilities = self.registry.all_capabilities()
        except Exception:
            self._capabilities = {}
        return dict(self._capabilities)

    def health(self) -> dict[str, Any]:
        try:
            h = self.provider.health()
            return {
                "healthy": bool(getattr(h, "healthy", True)),
                "provider": getattr(h, "name", self.provider.name),
                "message": getattr(h, "message", ""),
                "failures": getattr(h, "failures", 0),
                "lifecycle": self.lifecycle.phase.value,
                "enabled": self.config.enabled,
                "mode": self.config.mode.value,
            }
        except Exception as exc:
            return {"healthy": False, "message": str(exc)}

    def to_runtime_signals(self, profile: RuntimeProfile) -> dict[str, float]:
        return map_profile_to_runtime_signals(profile)

    def shutdown(self) -> None:
        try:
            self.lifecycle.transition(LifecyclePhase.SHUTDOWN)
            self.provider.shutdown()
        except Exception as exc:
            logger.warning("rpf shutdown failed: %s", exc)


def build_rpf(*, work_dir: Path | None = None, config: RPFRuntimeConfig | None = None) -> RuntimeProfilingFramework:
    cfg = config or load_rpf_config(work_dir=work_dir)
    lifecycle = ProfilingLifecycle()
    lifecycle.transition(LifecyclePhase.INITIALIZED)
    plugins = RPFPluginRegistry(cfg)
    registry = ProfilerRegistry(cfg)
    caps = registry.all_capabilities()
    lifecycle.transition(LifecyclePhase.CAPABILITY_DETECTED)
    provider = registry.select()
    try:
        provider.initialize()
    except Exception as exc:
        logger.warning("rpf provider initialize failed: %s", exc)
    telemetry = plugins.telemetry()
    exporter = plugins.exporter(telemetry=telemetry)
    # Ensure JSON store path exists even when exporter is composite
    store = ProfileStore(cfg.work_dir)
    feedback = ProfilerFeedbackService(store, cfg)
    traces = TraceRecorder(otel_enabled=cfg.otel_enabled)
    collector = ProfileCollector(
        cfg,
        provider,
        telemetry_meta=TelemetryMetadata(
            exporter=cfg.exporter,
            extensions={"provider": getattr(provider, "name", "")},
        ),
    )
    bus = ProfileSignalBus()
    connector = PhaseSignalConnector(bus)
    bus.bind(collector.record_phase)
    return RuntimeProfilingFramework(
        config=cfg,
        provider=provider,
        collector=collector,
        telemetry=telemetry,
        exporter=exporter,
        store=store,
        feedback=feedback,
        registry=registry,
        plugins=plugins,
        lifecycle=lifecycle,
        signal_bus=bus,
        connector=connector,
        traces=traces,
        _capabilities=caps,
    )


def build_rpf_at(work_dir: Path | str) -> RuntimeProfilingFramework:
    return build_rpf(work_dir=Path(work_dir))
