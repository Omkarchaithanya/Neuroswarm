"""Hardware / topology probe for affinity, NUMA, and device class."""

from __future__ import annotations

from typing import Any, Mapping

from ..interfaces.types import DeviceClass, ExecutionPlan, PoolKind
from .cpu_affinity_router import CpuAffinityRouter
from .numa_router import NumaRouter


class TopologyRouter:
    """Probe placement hints; Axion-safe when detector is missing or empty."""

    def __init__(
        self,
        hardware_cfg: Mapping[str, Any] | None = None,
        detector: Any | None = None,
    ) -> None:
        self.hardware_cfg = dict(hardware_cfg or {})
        self.detector = detector
        self.cpu_affinity = CpuAffinityRouter(self.hardware_cfg, detector=detector)
        self.numa = NumaRouter(self.hardware_cfg, detector=detector)

    def probe(self, plan: ExecutionPlan) -> dict[str, Any]:
        phase = PoolKind.PREFILL
        cores = self.cpu_affinity.recommend(phase, plan)
        numa_node = self.numa.node_for(plan)
        device = self._device_class()

        result: dict[str, Any] = {
            "affinity_cores": list(cores),
            "numa_node": int(numa_node),
            "device_class": device,
        }
        plan.affinity_cores = list(cores)
        plan.numa_node = int(numa_node)
        plan.device_class = device
        plan.metadata.setdefault("topology", {})
        plan.metadata["topology"].update(result)
        plan.scores["topology"] = 1.0 if cores else 0.5
        return result

    def _device_class(self) -> DeviceClass:
        preference = list(self.hardware_cfg.get("device_preference") or ["cpu"])
        features = dict(self.hardware_cfg.get("features") or {})
        allow = {
            "cpu": True,
            "gpu": bool(features.get("allow_gpu", True)),
            "npu": bool(features.get("allow_npu", True)),
            "cxl": bool(features.get("allow_cxl", True)),
            "sme": bool(features.get("allow_sme", True)),
        }

        detected: DeviceClass | None = None
        if self.detector is not None:
            try:
                raw = self.detector.device_class()
                if isinstance(raw, DeviceClass):
                    detected = raw
                else:
                    detected = DeviceClass(str(raw).lower())
            except Exception:  # noqa: BLE001 — fall through to preference
                detected = None

        if detected is not None and allow.get(detected.value, True):
            return detected

        for name in preference:
            key = str(name).lower()
            if not allow.get(key, False) and key != "cpu":
                continue
            try:
                return DeviceClass(key)
            except ValueError:
                continue
        return DeviceClass.CPU
