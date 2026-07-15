"""Proposal package — import strategies for side-effect registration."""

from __future__ import annotations

from .draft_model import DraftModelProposer
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
    "NgramProposer",
    "ProposalRegistry",
    "SelfSpeculationProposer",
    "SuffixProposer",
    "VerifierRegistry",
    "known_proposers",
    "known_verifiers",
    "register_proposer",
    "register_verifier",
]
