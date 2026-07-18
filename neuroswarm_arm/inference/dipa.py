"""Backward-compatible DIPA stub — prefer neuroswarm_arm.runtime.dipa."""

from __future__ import annotations

from neuroswarm_arm.runtime.dipa import DIPARuntime, build_dipa, load_dipa_config
from neuroswarm_arm.runtime.dipa.kernel import DIPARuntime as DIPA

__all__ = ["DIPA", "DIPARuntime", "build_dipa", "load_dipa_config"]
