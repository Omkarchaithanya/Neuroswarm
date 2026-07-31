"""AROP domain exceptions — fail loud, never silent defaults."""

from __future__ import annotations


class AropError(Exception):
    """Base for all AROP closed-loop tuner errors."""


class AropMetricMissing(AropError):
    """Expected JSON field is absent or null — stop the tuning cycle."""


class AropMetricInvalid(AropError):
    """Metric payload is present but dishonest or malformed (e.g. source=demo)."""


class AropContaminatedProfile(AropError):
    """Performix capture is contaminated (load-time syscall / unattributable symbols)."""


class AropClampViolation(AropError):
    """Proposed parameter value falls outside safe clamp bounds."""
