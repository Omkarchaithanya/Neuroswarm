"""Plugin bootstrap — import all strategies for registry side effects."""

from __future__ import annotations

# Working
import neuroswarm_arm.runtime.armcascade.proposal.draft_model  # noqa: F401
import neuroswarm_arm.runtime.armcascade.proposal.self_speculation  # noqa: F401
import neuroswarm_arm.runtime.armcascade.proposal.strategies  # noqa: F401
import neuroswarm_arm.runtime.armcascade.verification.strategies  # noqa: F401
import neuroswarm_arm.runtime.armcascade.verification.logits_verifier  # noqa: F401

# Stubs
import neuroswarm_arm.runtime.armcascade.proposal.stubs  # noqa: F401
import neuroswarm_arm.runtime.armcascade.verification.stubs  # noqa: F401


def load_plugins() -> None:
    """Explicit entrypoint for factory / tests."""
    return None
