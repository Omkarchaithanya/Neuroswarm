"""AROP v1 — rule-based Performix-driven cascade tuner (dry-run default).

Independent of neuroswarm_arm.evolution RuntimeOptimizer / GEPA / Mem0 / RL.
Consumes apx JSON + benchmark outputs; never invents metrics.
"""

from __future__ import annotations

from neuroswarm_arm.arop.exceptions import (
    AropClampViolation,
    AropContaminatedProfile,
    AropError,
    AropMetricInvalid,
    AropMetricMissing,
)

__all__ = [
    "AropClampViolation",
    "AropContaminatedProfile",
    "AropError",
    "AropMetricInvalid",
    "AropMetricMissing",
]
