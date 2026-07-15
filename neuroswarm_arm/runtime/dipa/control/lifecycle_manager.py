"""LifecycleManager — ordered start/drain/stop for DIPA control plane."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Mapping

from neuroswarm_arm.runtime.dipa.interfaces.lifecycle import ILifecycle, LifecyclePhase


class LifecycleManager(ILifecycle):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._phase = LifecyclePhase.CREATED
        self._hooks: dict[LifecyclePhase, list[Callable[[], None]]] = {
            p: [] for p in LifecyclePhase
        }
        self._error: str | None = None
        self._started_at: float | None = None

    def on(self, phase: LifecyclePhase, hook: Callable[[], None]) -> None:
        with self._lock:
            self._hooks[phase].append(hook)

    def phase(self) -> LifecyclePhase:
        with self._lock:
            return self._phase

    def set_phase(self, phase: LifecyclePhase) -> None:
        with self._lock:
            self._phase = phase
            for hook in list(self._hooks.get(phase, [])):
                try:
                    hook()
                except Exception as exc:
                    self._error = str(exc)
                    self._phase = LifecyclePhase.FAILED
                    raise

    def start(self) -> None:
        """Run canonical boot sequence phases (hooks registered by factory)."""
        with self._lock:
            if self._phase == LifecyclePhase.READY:
                return
            self._started_at = time.time()
        try:
            for phase in (
                LifecyclePhase.DETECTING,
                LifecyclePhase.AFFINITY,
                LifecyclePhase.BACKENDS,
                LifecyclePhase.MODELS,
                LifecyclePhase.WARMUP,
                LifecyclePhase.READY,
            ):
                self.set_phase(phase)
        except Exception:
            self.set_phase(LifecyclePhase.FAILED)
            raise

    def drain(self, timeout_s: float = 30.0) -> None:
        self.set_phase(LifecyclePhase.DRAINING)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(0.05)
            break

    def stop(self) -> None:
        if self._phase not in {LifecyclePhase.STOPPED, LifecyclePhase.FAILED}:
            try:
                self.drain()
            except Exception:
                pass
        self.set_phase(LifecyclePhase.STOPPED)

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "phase": self._phase.value,
                "error": self._error,
                "started_at": self._started_at,
                "uptime_s": (time.time() - self._started_at) if self._started_at else 0.0,
            }
