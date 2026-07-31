"""CPU affinity recommendations — prefers fixed UMA partitions on Axion."""

from __future__ import annotations

import os
from typing import Any, Mapping

from ..interfaces.types import ExecutionPlan, PoolKind


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


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
        self.mode = str(partition.get("mode", "auto")).lower()
        self.uma_draft = [int(c) for c in (partition.get("uma_draft") or [0, 1])]
        self.uma_verify_mid = [
            int(c) for c in (partition.get("uma_verify_mid") or [2, 3, 4])
        ]
        self.uma_verify_large = [
            int(c) for c in (partition.get("uma_verify_large") or [5, 6, 7])
        ]
        self.prefill_fraction = float(partition.get("prefill_fraction", 0.4))
        self.decode_fraction = float(partition.get("decode_fraction", 0.6))
        self.enabled = bool(self.hardware_cfg.get("affinity_enabled", True))

    def recommend(
        self, phase: PoolKind | str, plan: ExecutionPlan | None = None
    ) -> list[int]:
        if not self.enabled:
            return []
        if not _env_bool("NSA_DRAFT_VERIFY_AFFINITY", True):
            return []

        kind = phase.value if isinstance(phase, PoolKind) else str(phase).lower()
        speculative = self._speculation_enabled(plan)

        # Spec decoding path: draft → uma_draft, verify → uma_verify_large (+ mid).
        if speculative and kind in {"draft", PoolKind.PREFILL.value, "prefill"}:
            selected = list(self.uma_draft)
            if plan is not None and not plan.affinity_cores:
                plan.affinity_cores = list(selected)
            self._stamp_plan(plan, draft=selected, verify=None)
            return selected
        if speculative and kind in {
            "verify",
            PoolKind.DECODE.value,
            "decode",
            PoolKind.STREAM.value,
            "stream",
        }:
            selected = list(self.uma_verify_large) or (
                list(self.uma_verify_mid) + list(self.uma_verify_large)
            )
            # Prefer large; fall back to mid+large when large empty.
            if not selected:
                selected = list(self.uma_verify_mid) + list(self.uma_verify_large)
            self._stamp_plan(plan, draft=None, verify=selected)
            return selected

        # Prefer explicit UMA partitions when configured (Axion path).
        if self.mode in {"auto", "uma_fixed", "uma_affinity"}:
            try:
                from neuroswarm_arm.runtime.haoe.topology.numa_status import (
                    collect_numa_status,
                )

                st = collect_numa_status()
                if st.locality_mode == "cache_aware" and st.core_partitions:
                    if kind in {PoolKind.PREFILL.value, "prefill", "draft"}:
                        selected = list(st.core_partitions.get("tier1") or self.uma_draft)
                    else:
                        selected = list(
                            st.core_partitions.get("tier2")
                            or self.uma_verify_mid
                        )
                    if plan is not None and kind in {
                        PoolKind.PREFILL.value,
                        "prefill",
                        "draft",
                    }:
                        if not plan.affinity_cores:
                            plan.affinity_cores = list(selected)
                    return selected
            except Exception:  # noqa: BLE001
                pass
            if kind in {PoolKind.PREFILL.value, "prefill", "draft"}:
                return list(self.uma_draft)
            if kind in {PoolKind.DECODE.value, "decode", PoolKind.STREAM.value, "verify"}:
                return list(self.uma_verify_mid) + list(self.uma_verify_large)

        cores = self._core_ids()
        if not cores:
            return []

        n = len(cores)
        prefill_n = max(1, int(round(n * self.prefill_fraction)))
        prefill_n = min(prefill_n, n - 1) if n > 1 else n
        decode_start = prefill_n

        if kind in {PoolKind.PREFILL.value, "prefill", "draft"}:
            selected = cores[:prefill_n]
        elif kind in {PoolKind.DECODE.value, "decode", PoolKind.STREAM.value, "verify"}:
            selected = cores[decode_start:] or cores[-max(1, n // 2) :]
        else:
            selected = list(cores)

        if plan is not None and kind in {PoolKind.PREFILL.value, "prefill", "draft"}:
            if not plan.affinity_cores:
                plan.affinity_cores = list(selected)
        return list(selected)

    @staticmethod
    def _speculation_enabled(plan: ExecutionPlan | None) -> bool:
        if plan is None:
            return False
        if not getattr(plan, "speculation", False):
            return False
        meta = dict(getattr(plan, "metadata", None) or {})
        spec = meta.get("speculation") or {}
        if isinstance(spec, dict) and "enabled" in spec:
            return bool(spec.get("enabled"))
        return True

    @staticmethod
    def _stamp_plan(
        plan: ExecutionPlan | None,
        *,
        draft: list[int] | None,
        verify: list[int] | None,
    ) -> None:
        if plan is None:
            return
        topo = plan.metadata.setdefault("topology", {})
        if not isinstance(topo, dict):
            return
        if draft is not None:
            topo["affinity_draft"] = list(draft)
            topo.setdefault("affinity_cores", list(draft))
        if verify is not None:
            topo["affinity_verify"] = list(verify)

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
        raw = self.hardware_cfg.get("cores") or self.hardware_cfg.get("affinity_cores")
        if isinstance(raw, (list, tuple)) and raw:
            return [int(c) for c in raw]
        return []
