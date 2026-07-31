"""Minimal reasoning-trace emit helpers for ASCR / DIPA (no heavy deps)."""

from __future__ import annotations

from typing import Any, Mapping


def tier_model_name(tier_id: int | str | None) -> str:
    tid = int(tier_id or 1)
    return f"tier{tid}"


def tier_quant_label(tier_id: int | str | None = None) -> str:
    return "Q4_0"


def trace_emit(
    target: Any,
    session_id: str,
    kind: str,
    data: Mapping[str, Any] | None = None,
) -> None:
    """Best-effort emit into an optional emitter; never raises."""
    if not session_id:
        return
    emitter = getattr(target, "emit", None) or getattr(target, "trace", None)
    if callable(emitter):
        try:
            emitter(session_id, kind, dict(data or {}))
        except Exception:
            return
