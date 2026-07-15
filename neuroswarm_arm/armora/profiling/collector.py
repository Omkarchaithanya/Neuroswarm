"""Session collector — correlates request/execution/envelope IDs."""

from __future__ import annotations

import logging
import threading
from typing import Any

from .config import RPFRuntimeConfig
from .reports import ProfileReportBuilder
from .schemas import (
    MetricBatch,
    PhaseTimings,
    ProfileSessionContext,
    ProfilingMode,
    RuntimeProfile,
    TelemetryMetadata,
    new_id,
)

logger = logging.getLogger(__name__)


class ProfileSessionState:
    __slots__ = ("context", "phases", "batches", "warnings", "disabled")

    def __init__(self, context: ProfileSessionContext) -> None:
        self.context = context
        self.phases = PhaseTimings()
        self.batches: list[MetricBatch] = []
        self.warnings: list[str] = []
        self.disabled = False


class ProfileCollector:
    """IProfileCollector implementation — never raises into inference."""

    def __init__(
        self,
        cfg: RPFRuntimeConfig,
        provider: Any,
        *,
        report_builder: ProfileReportBuilder | None = None,
        telemetry_meta: TelemetryMetadata | None = None,
    ) -> None:
        self.cfg = cfg
        self.provider = provider
        self.reports = report_builder or ProfileReportBuilder()
        self.telemetry_meta = telemetry_meta or TelemetryMetadata(
            exporter=cfg.exporter,
        )
        self._lock = threading.RLock()
        self._sessions: dict[str, ProfileSessionState] = {}

    def open_session(self, **kwargs: Any) -> ProfileSessionContext:
        try:
            if not self.cfg.enabled or self.cfg.mode == ProfilingMode.DISABLED:
                ctx = ProfileSessionContext(
                    session_id=new_id(),
                    mode=ProfilingMode.DISABLED,
                    sampling_hz=0.0,
                    request_id=str(kwargs.get("request_id", "")),
                    execution_id=str(kwargs.get("execution_id") or new_id()),
                    workflow_id=str(kwargs.get("workflow_id", "")),
                    agent_id=str(kwargs.get("agent_id", "")),
                    envelope_id=str(kwargs.get("envelope_id", "")),
                    tenant_id=str(kwargs.get("tenant_id", "")),
                )
                state = ProfileSessionState(ctx)
                state.disabled = True
                with self._lock:
                    self._sessions[ctx.session_id] = state
                return ctx

            mode = kwargs.get("mode", self.cfg.mode)
            if isinstance(mode, str):
                try:
                    mode = ProfilingMode(mode)
                except Exception:
                    mode = self.cfg.mode
            ctx = ProfileSessionContext(
                request_id=str(kwargs.get("request_id", "")),
                execution_id=str(kwargs.get("execution_id") or new_id()),
                workflow_id=str(kwargs.get("workflow_id", "")),
                agent_id=str(kwargs.get("agent_id", "")),
                envelope_id=str(kwargs.get("envelope_id", "")),
                tenant_id=str(kwargs.get("tenant_id", "")),
                mode=mode,
                sampling_hz=float(kwargs.get("sampling_hz", self.cfg.sample_hz)),
                extensions=dict(kwargs.get("extensions") or {}),
            )
            state = ProfileSessionState(ctx)
            with self._lock:
                self._sessions[ctx.session_id] = state
            try:
                self.provider.start(ctx)
            except Exception as exc:
                state.warnings.append(f"provider.start failed: {exc}")
                logger.warning("rpf provider.start failed: %s", exc)
            return ctx
        except Exception as exc:
            logger.warning("rpf open_session failed: %s", exc)
            ctx = ProfileSessionContext(mode=ProfilingMode.DISABLED, sampling_hz=0.0)
            state = ProfileSessionState(ctx)
            state.disabled = True
            state.warnings.append(str(exc))
            with self._lock:
                self._sessions[ctx.session_id] = state
            return ctx

    def record_phase(self, session_id: str, **timings: Any) -> None:
        try:
            with self._lock:
                state = self._sessions.get(session_id)
                if state is None or state.disabled:
                    return
                for key, value in timings.items():
                    if key == "extensions" and isinstance(value, dict):
                        state.phases.extensions.update(value)
                        continue
                    if hasattr(state.phases, key):
                        try:
                            setattr(state.phases, key, type(getattr(state.phases, key))(value))
                        except Exception:
                            try:
                                setattr(state.phases, key, value)
                            except Exception:
                                pass
                    else:
                        state.phases.extensions[key] = value
        except Exception as exc:
            logger.warning("rpf record_phase failed: %s", exc)

    def sample(self, session_id: str) -> MetricBatch:
        try:
            with self._lock:
                state = self._sessions.get(session_id)
                if state is None or state.disabled:
                    return MetricBatch(samples=[], provider="none", session_id=session_id)
                ctx = state.context
            batch = self.provider.sample(ctx)
            with self._lock:
                st = self._sessions.get(session_id)
                if st is not None:
                    st.batches.append(batch)
            return batch
        except Exception as exc:
            logger.warning("rpf sample failed: %s", exc)
            return MetricBatch(samples=[], provider="error", session_id=session_id)

    def finalize(self, session_id: str) -> RuntimeProfile:
        try:
            with self._lock:
                state = self._sessions.pop(session_id, None)
            if state is None:
                return RuntimeProfile(
                    profiler_used="none",
                    warnings=["session not found"],
                    mode=ProfilingMode.DISABLED,
                )
            if not state.disabled:
                try:
                    stop_batch = self.provider.stop(state.context)
                    state.batches.append(stop_batch)
                except Exception as exc:
                    state.warnings.append(f"provider.stop failed: {exc}")
            recs: list[str] = []
            fn = getattr(self.provider, "recommendations", None)
            if callable(fn):
                try:
                    recs = list(fn())
                except Exception:
                    recs = []
            profiler_name = str(getattr(self.provider, "name", "unknown"))
            return self.reports.build(
                state.context,
                batches=state.batches,
                phases=state.phases,
                profiler_used=profiler_name,
                recommendations=recs,
                warnings=state.warnings,
                telemetry=self.telemetry_meta,
            )
        except Exception as exc:
            logger.warning("rpf finalize failed: %s", exc)
            return RuntimeProfile(
                profiler_used="error",
                warnings=[str(exc)],
                mode=ProfilingMode.DISABLED,
            )

    def get_session(self, session_id: str) -> ProfileSessionContext | None:
        with self._lock:
            st = self._sessions.get(session_id)
            return st.context if st else None
