from __future__ import annotations

<<<<<<< HEAD
"""Legacy AQR entry — prefer ``neuroswarm_arm.runtime.aqr.pick_quant_primary``."""
=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84

QUANT_BY_ROLE = {
    "reasoning": "Q5_K_M",
    "tool_call": "Q4_0",
    "summarization": "Q4_0",
    "code": "Q5_K_M",
    "classification": "Q4_0",
}


def pick_quant(agent_role: str, workload_class: str | None = None) -> str:
    if workload_class and workload_class in QUANT_BY_ROLE:
        return QUANT_BY_ROLE[workload_class]
    return QUANT_BY_ROLE.get(agent_role, "Q5_K_M")

