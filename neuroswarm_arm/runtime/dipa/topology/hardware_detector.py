"""Hardware detector for DIPA pools."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .feature_detector import FeatureDetector


@dataclass
class HardwareSnapshot:
    cpu_count: int
    core_ids: list[int]
    prefill_cores: list[int]
    decode_cores: list[int]
    features: dict[str, object] = field(default_factory=dict)


class HardwareDetector:
    def __init__(
        self,
        *,
        prefill_fraction: float = 0.4,
        override_cores: list[int] | None = None,
    ) -> None:
        self.prefill_fraction = prefill_fraction
        self.override_cores = override_cores

    def detect(self) -> HardwareSnapshot:
        if self.override_cores is not None:
            cores = list(self.override_cores)
        else:
            n = os.cpu_count() or 4
            cores = list(range(n))
        split = max(1, int(len(cores) * self.prefill_fraction))
        features = {
            k: v.value for k, v in FeatureDetector().detect().items()
        }
        return HardwareSnapshot(
            cpu_count=len(cores),
            core_ids=cores,
            prefill_cores=cores[:split],
            decode_cores=cores[split:] or cores[:],
            features=features,
        )
