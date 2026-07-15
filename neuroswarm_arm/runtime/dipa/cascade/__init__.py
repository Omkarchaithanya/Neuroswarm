"""DIPA cascade subsystem — compatibility shim over ASCR (ADR-0008).

Prefer ``neuroswarm_arm.runtime.armcascade`` for new code.
"""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.engine import ASCREngine
from neuroswarm_arm.runtime.armcascade.factory import build_ascr

from .cascade_engine import CascadeEngine
from .cascade_executor import CascadeExecutor, approx_tokens, build_messages
from .cascade_policy import (
    CascadeFallbackPolicy,
    CascadePolicy,
    SpeculationPolicy,
    TierPolicy,
)
from .cascade_validator import CascadeValidator, accepts
from .self_speculation import SelfSpeculationEngine
from .verifier import DEFAULT_CONFIDENCE_CFG, Verifier, confidence

# ASCR is the production ICascadeEngine implementation.
CascadeEngineASCR = ASCREngine

__all__ = [
    "ASCREngine",
    "CascadeEngine",
    "CascadeEngineASCR",
    "CascadeExecutor",
    "CascadeFallbackPolicy",
    "CascadePolicy",
    "CascadeValidator",
    "DEFAULT_CONFIDENCE_CFG",
    "SelfSpeculationEngine",
    "SpeculationPolicy",
    "TierPolicy",
    "Verifier",
    "accepts",
    "approx_tokens",
    "build_ascr",
    "build_messages",
    "confidence",
]
