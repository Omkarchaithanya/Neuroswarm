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

