"""Capability providers for DIPA registry."""

from __future__ import annotations

from typing import Any, Mapping

from ..topology.hardware_detector import HardwareSnapshot


class HardwareProvider:
    def __init__(self, snapshot: HardwareSnapshot) -> None:
        self.snapshot = snapshot

    def cores(self) -> list[int]:
        return list(self.snapshot.core_ids)

    def features(self) -> Mapping[str, Any]:
        return dict(self.snapshot.features)
