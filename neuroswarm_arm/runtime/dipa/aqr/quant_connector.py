"""AQR quant connector — wraps Layer-3 policy; DIPA never hardcodes quant."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces.quantizer import IQuantConnector
from ..interfaces.types import InferenceRequest, QuantLevel, WorkloadClass

# Future formats registered but unsupported until AQR enables them.
_FUTURE_UNSUPPORTED = {QuantLevel.FP8.value, QuantLevel.MXFP.value}

_DEFAULT_BY_WORKLOAD = {
    WorkloadClass.REASONING: "Q5_K_M",
    WorkloadClass.CODING: "Q5_K_M",
    WorkloadClass.TOOL_CALLING: "Q4_0",
    WorkloadClass.CLASSIFICATION: "Q4_0",
    WorkloadClass.EMBEDDING: "Q4_0",
    WorkloadClass.RERANKING: "Q4_0",
    WorkloadClass.VISION: "Q5_K_M",
    WorkloadClass.SPEECH: "Q4_K_M",
}

_ROLE_MAP = {
    "reasoning": "Q5_K_M",
    "tool_call": "Q4_0",
    "summarization": "Q4_0",
    "code": "Q5_K_M",
    "classification": "Q4_0",
}


class AQRQuantConnector(IQuantConnector):
    """Port to Adaptive Quantization Router.

    Prefers injected callable (``neuroswarm_arm.aqr.pick_quant``) when provided;
    otherwise uses YAML/role tables. FP8/MXFP listed but rejected until supported.
    """

    def __init__(
        self,
        pick_fn: Any | None = None,
        *,
        available: list[str] | None = None,
        role_map: Mapping[str, str] | None = None,
    ) -> None:
        self._pick_fn = pick_fn
        self._role_map = dict(role_map or _ROLE_MAP)
        self._available = list(
            available
            or [
                "Q2",
                "Q3",
                "Q4",
                "Q4_0",
                "Q4_K_M",
                "Q5",
                "Q5_K_M",
                "Q6",
                "Q8_0",
                "INT8",
                "FP16",
                "BF16",
                "FP8",
                "MXFP",
            ]
        )

    def choose(
        self,
        req: InferenceRequest,
        workload: WorkloadClass,
        *,
        constraints: Mapping[str, Any] | None = None,
    ) -> str:
        constraints = constraints or {}
        if self._pick_fn is not None:
            quant = str(
                self._pick_fn(req.agent_role, workload.value)
                or self._pick_fn(req.agent_role, None)
            )
        else:
            quant = self._role_map.get(
                req.agent_role, _DEFAULT_BY_WORKLOAD.get(workload, "Q5_K_M")
            )
        forced = constraints.get("quant")
        if forced:
            quant = str(forced)
        if quant in _FUTURE_UNSUPPORTED or not self.is_supported(quant):
            quant = _DEFAULT_BY_WORKLOAD.get(workload, "Q5_K_M")
        return quant

    def available(self) -> list[str]:
        return list(self._available)

    def is_supported(self, quant: str) -> bool:
        if quant in _FUTURE_UNSUPPORTED:
            return False
        return quant in self._available
