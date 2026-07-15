"""Adaptive Context Runtime (Context Operating System) — ArmCascade Layer 4.

Not RAG. Not a vector DB. Mem0 = cognitive memory runtime; OKF = knowledge OS.
Mission: smallest high-information context that preserves task-required facts.
Compression is measured (ratio, retention, latency) — no fixed percentage claim.

Distinct from AWPP (5-layer stack Layer 4 pre-warm predictor), which may consume ACR hints.
"""

from neuroswarm_arm.runtime.acr.config import ACRConfig, load_acr_config
from neuroswarm_arm.runtime.acr.factory import build_acr
from neuroswarm_arm.runtime.acr.ir import (
    ContextRequirementGraph,
    ContextSnapshot,
    ContextStatistics,
    RetrievalExecutionPlan,
)
from neuroswarm_arm.runtime.acr.kernel import AdaptiveContextRuntime

__all__ = [
    "ACRConfig",
    "AdaptiveContextRuntime",
    "ContextRequirementGraph",
    "ContextSnapshot",
    "ContextStatistics",
    "RetrievalExecutionPlan",
    "build_acr",
    "load_acr_config",
]
