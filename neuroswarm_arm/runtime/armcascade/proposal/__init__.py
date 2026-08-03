"""Proposal package — import strategies for side-effect registration."""

from __future__ import annotations

from .draft_model import DraftModelProposer
from .draft_registry import DraftModelRegistry, detect_host_arch
from .ngram_cache import NgramCache
from .registry import (
    ProposalRegistry,
    VerifierRegistry,
    known_proposers,
    known_verifiers,
    register_proposer,
    register_verifier,
)
from .self_speculation import NgramProposer, SelfSpeculationProposer, SuffixProposer

# Optional proposers — may be absent on partial checkouts / WIP branches.
try:
    from .eagle3 import Eagle3Proposer
except ImportError:  # pragma: no cover
    Eagle3Proposer = None  # type: ignore[misc, assignment]
try:
    from .medusa import MedusaProposer
except ImportError:  # pragma: no cover
    MedusaProposer = None  # type: ignore[misc, assignment]

# Ensure working proposers register on import.
__all__ = [
    "DraftModelProposer",
    "DraftModelRegistry",
    "Eagle3Proposer",
    "MedusaProposer",
    "NgramCache",
    "NgramProposer",
    "ProposalRegistry",
    "SelfSpeculationProposer",
    "SuffixProposer",
    "VerifierRegistry",
    "detect_host_arch",
    "known_proposers",
    "known_verifiers",
    "register_proposer",
    "register_verifier",
]
