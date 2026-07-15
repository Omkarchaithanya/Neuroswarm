"""CPU affinity recommendations for prefill/decode phases."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces.types import ExecutionPlan, PoolKind


class CpuAffinityRouter:
    """Recommend logical core partitions for a phase (homogeneous Axion-safe)."""

    def __init__(
        self,
        hardware_cfg: Mapping[str, Any] | None = None,
        detector: Any | None = None,
    ) -> None:
        self.hardware_cfg = dict(hardware_cfg or {})
        self.detector = detector
        partition = dict(self.hardware_cfg.get("core_partition") or {})
        self.prefill_fraction = float(partition.get("prefill_fraction", 0.4))
        self.decode_fraction = float(partition.get("decode_fraction", 0.6))
        self.enabled = bool(self.hardware_cfg.get("affinity_enabled", True))

    def recommend(
        self, phase: PoolKind | str, plan: ExecutionPlan | None = None
    ) -> list[int]:
        if not self.enabled:
            return []

        cores = self._core_ids()
        if not cores:
            return []

        kind = phase.value if isinstance(phase, PoolKind) else str(phase).lower()
        n = len(cores)
        prefill_n = max(1, int(round(n * self.prefill_fraction)))
        prefill_n = min(prefill_n, n - 1) if n > 1 else n
        decode_start = prefill_n

        if kind in {PoolKind.PREFILL.value, "prefill"}:
            selected = cores[:prefill_n]
        elif kind in {PoolKind.DECODE.value, "decode", PoolKind.STREAM.value}:
            selected = cores[decode_start:] or cores[-max(1, n // 2) :]
        else:
            selected = list(cores)

        if plan is not None and kind in {PoolKind.PREFILL.value, "prefill"}:
            # Seed plan affinity when probing prefill first.
            if not plan.affinity_cores:
                plan.affinity_cores = list(selected)
        return list(selected)

    def _core_ids(self) -> list[int]:
        if self.detector is not None:
            for method in ("core_ids", "logical_cores", "available_cores"):
                fn = getattr(self.detector, method, None)
                if callable(fn):
                    try:
                        ids = list(fn())
                        if ids:
                            return [int(c) for c in ids]
                    except Exception:  # noqa: BLE001
                        pass
        # Explicit override list in hardware.yaml (optional).
        raw = self.hardware_cfg.get("cores") or self.hardware_cfg.get("affinity_cores")
        if isinstance(raw, (list, tuple)) and raw:
            return [int(c) for c in raw]
        return []
