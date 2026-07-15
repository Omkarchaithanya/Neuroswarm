"""Plane-2 compatibility facade — delegates pressure/telemetry to MAKS Memory OS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.maks.manager import KVManager
    from neuroswarm_arm.runtime.kv.manager.runtime import KVRuntimeManager


def bind_maks_pressure(kv_runtime: KVRuntimeManager, maks: KVManager) -> None:
    """Monkey-patch / wrap pressure_snapshot so peers reading Plane-2 see MAKS pressure."""
    original = kv_runtime.pressure_snapshot

    def _merged() -> Any:
        try:
            maks_snap = maks.pressure_snapshot()
        except Exception:
            return original()
        try:
            plane = original()
            if hasattr(plane, "__dict__"):
                # PressureSnapshot dataclass-like
                try:
                    plane.pressure = float(maks_snap.get("pressure", getattr(plane, "pressure", 0.0)))
                    if hasattr(plane, "used_bytes"):
                        plane.used_bytes = int(maks_snap.get("used_bytes", plane.used_bytes))
                except Exception:
                    pass
                return plane
            if isinstance(plane, dict):
                out = dict(plane)
                out.update(
                    {
                        "pressure": maks_snap.get("pressure", out.get("pressure", 0.0)),
                        "used_bytes": maks_snap.get("used_bytes", out.get("used_bytes", 0)),
                        "maks": maks_snap,
                    }
                )
                return out
        except Exception:
            pass
        return maks_snap

    kv_runtime.pressure_snapshot = _merged  # type: ignore[method-assign]
    # Stash for debugging / unbind
    setattr(kv_runtime, "_maks_pressure_source", maks)
    setattr(kv_runtime, "_plane2_pressure_original", original)


def maks_pressure_callable(maks: KVManager) -> Callable[[], dict[str, Any]]:
    """HAOE / RTG injectable pressure callback."""
    return maks.pressure_monitor
