<<<<<<< HEAD
"""Backward-compatible DIPA stub — prefer neuroswarm_arm.runtime.dipa."""

from __future__ import annotations

from neuroswarm_arm.runtime.dipa import DIPARuntime, build_dipa, load_dipa_config
from neuroswarm_arm.runtime.dipa.kernel import DIPARuntime as DIPA

__all__ = ["DIPA", "DIPARuntime", "build_dipa", "load_dipa_config"]
=======
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DIPA:
    def route(self, phase: str, batch_size: int = 1, is_reasoning: bool = False) -> str:
        if phase == "prefill" and batch_size > 16:
            return "vllm_int4_high_throughput"
        if phase == "decode" and batch_size == 1:
            return "llama_cpp_kleidiai_arm"
        if is_reasoning:
            return "cascade_tier_2_then_3"
        return "llama_cpp_kleidiai_arm"

>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
