"""ArmCascade Adaptive Speculative Cascade Runtime (ASCR)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.armcascade.engine import ASCREngine


def build_ascr(*args: Any, **kwargs: Any):
    from neuroswarm_arm.runtime.armcascade.factory import build_ascr as _build

    return _build(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name == "ASCREngine":
        from neuroswarm_arm.runtime.armcascade.engine import ASCREngine

        return ASCREngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ASCREngine", "build_ascr"]
