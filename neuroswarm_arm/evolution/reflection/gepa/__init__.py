"""
GEPA reflection subsystem for AROP Plane 5.

Official GEPA (Genetic-Pareto): reflective evolution of **textual** components
via ASI → reflection → mutation → Pareto → merge.
https://github.com/gepa-ai/gepa · https://gepa-ai.github.io/gepa/

This package is NOT:
- an RL algorithm (PPO/SAC)
- a hardware / NUMA / thread optimizer
- an ArmCascade redesign
- an ARMORA replacement

Numeric runtime knobs stay in RuleBasedReflectionStrategy (non-GEPA).
"""

from neuroswarm_arm.evolution.reflection.gepa.adapter import NexusGEPAAdapter, OfficialGEPABridge
from neuroswarm_arm.evolution.reflection.gepa.asi import ASIBuilder, ActionableSideInformation, ReflectiveRecord
from neuroswarm_arm.evolution.reflection.gepa.candidate import CandidatePool, TextCandidate
from neuroswarm_arm.evolution.reflection.gepa.deployment import ApprovalGate, TextArtifactDeployer
from neuroswarm_arm.evolution.reflection.gepa.evaluation import EvaluationBatch
from neuroswarm_arm.evolution.reflection.gepa.facade import GEPAFacade, GEPAOptimizeResult
from neuroswarm_arm.evolution.reflection.gepa.merge import SystemAwareMergeEngine
from neuroswarm_arm.evolution.reflection.gepa.mutation import (
    HttpReflectionLM,
    MockReflectionLM,
    ReflectiveMutationEngine,
    build_reflection_lm,
)
from neuroswarm_arm.evolution.reflection.gepa.pareto import ParetoFront

__all__ = [
    "ASIBuilder",
    "ActionableSideInformation",
    "ApprovalGate",
    "CandidatePool",
    "EvaluationBatch",
    "GEPAFacade",
    "GEPAOptimizeResult",
    "HttpReflectionLM",
    "MockReflectionLM",
    "NexusGEPAAdapter",
    "OfficialGEPABridge",
    "ParetoFront",
    "ReflectiveMutationEngine",
    "ReflectiveRecord",
    "SystemAwareMergeEngine",
    "TextArtifactDeployer",
    "TextCandidate",
    "build_reflection_lm",
]
