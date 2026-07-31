"""MLX backend for Apple Silicon (M3/M4/M5) native inference."""

from __future__ import annotations

from .backend import MlxBackend
from .spec import MlxSpecController

__all__ = ["MlxBackend", "MlxSpecController"]
