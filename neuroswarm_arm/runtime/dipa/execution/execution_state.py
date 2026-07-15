"""Execution state machine helpers."""

from __future__ import annotations

from ..interfaces.types import ExecutionPhase

TRANSITIONS: dict[ExecutionPhase, set[ExecutionPhase]] = {
    ExecutionPhase.ADMITTED: {
        ExecutionPhase.PLANNED,
        ExecutionPhase.FAILED,
        ExecutionPhase.CANCELLED,
    },
    ExecutionPhase.PLANNED: {ExecutionPhase.CLASSIFIED, ExecutionPhase.FAILED},
    ExecutionPhase.CLASSIFIED: {ExecutionPhase.INTENT_DETECTED, ExecutionPhase.FAILED},
    ExecutionPhase.INTENT_DETECTED: {
        ExecutionPhase.MODEL_SELECTED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.MODEL_SELECTED: {
        ExecutionPhase.BACKEND_SELECTED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.BACKEND_SELECTED: {
        ExecutionPhase.HARDWARE_PROBED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.HARDWARE_PROBED: {
        ExecutionPhase.POLICY_APPLIED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.POLICY_APPLIED: {
        ExecutionPhase.QUANT_RESOLVED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.QUANT_RESOLVED: {
        ExecutionPhase.WARM_CHECKED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.WARM_CHECKED: {ExecutionPhase.KV_ATTACHED, ExecutionPhase.FAILED},
    ExecutionPhase.KV_ATTACHED: {
        ExecutionPhase.CASCADE,
        ExecutionPhase.PREFILL,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.CASCADE: {
        ExecutionPhase.PREFILL,
        ExecutionPhase.DECODE,
        ExecutionPhase.STREAMING,
        ExecutionPhase.RECOVERING,
        ExecutionPhase.COMPLETED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.PREFILL: {
        ExecutionPhase.DECODE,
        ExecutionPhase.RECOVERING,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.DECODE: {
        ExecutionPhase.STREAMING,
        ExecutionPhase.METRICS,
        ExecutionPhase.RECOVERING,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.STREAMING: {
        ExecutionPhase.METRICS,
        ExecutionPhase.RECOVERING,
        ExecutionPhase.COMPLETED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.METRICS: {ExecutionPhase.COMPLETED, ExecutionPhase.FAILED},
    ExecutionPhase.RECOVERING: {
        ExecutionPhase.BACKEND_SELECTED,
        ExecutionPhase.MODEL_SELECTED,
        ExecutionPhase.QUANT_RESOLVED,
        ExecutionPhase.DEGRADED,
        ExecutionPhase.FAILED,
    },
    ExecutionPhase.DEGRADED: {ExecutionPhase.METRICS, ExecutionPhase.COMPLETED},
    ExecutionPhase.COMPLETED: set(),
    ExecutionPhase.FAILED: set(),
    ExecutionPhase.CANCELLED: set(),
}


def can_transition(src: ExecutionPhase, dst: ExecutionPhase) -> bool:
    return dst in TRANSITIONS.get(src, set()) or src == dst


def advance(src: ExecutionPhase, dst: ExecutionPhase) -> ExecutionPhase:
    if not can_transition(src, dst):
        return dst
    return dst
