"""Proposal package — import strategies for side-effect registration."""

from __future__ import annotations

from .draft_model import DraftModelProposer
from .draft_registry import DraftModelRegistry, detect_host_arch
from .eagle3 import Eagle3Proposer
from .medusa import MedusaProposer
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
