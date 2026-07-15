"""AQR runtime package — adaptive quantization routing."""

from __future__ import annotations

from neuroswarm_arm.aqr import QUANT_BY_ROLE, pick_quant


def pick_quant_primary(agent_role: str, workload_class: str | None = None) -> str:
    """Primary quant picker used by DIPA (alias over catalog-aware path later)."""
    return pick_quant(agent_role, workload_class)


__all__ = ["QUANT_BY_ROLE", "pick_quant", "pick_quant_primary"]
