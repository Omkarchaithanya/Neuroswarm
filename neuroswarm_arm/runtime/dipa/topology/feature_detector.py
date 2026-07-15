"""Feature detector — AVAILABLE / UNAVAILABLE / UNKNOWN (Axion-safe)."""

from __future__ import annotations

import os
import platform
from pathlib import Path

from ..interfaces.types import FeatureStatus


class FeatureDetector:
    def detect(self) -> dict[str, FeatureStatus]:
        features = {
            "arm": FeatureStatus.UNKNOWN,
            "sve2": FeatureStatus.UNKNOWN,
            "sme": FeatureStatus.UNKNOWN,
            "dotprod": FeatureStatus.UNKNOWN,
            "i8mm": FeatureStatus.UNKNOWN,
            "mte": FeatureStatus.UNAVAILABLE,
            "cxl": FeatureStatus.UNAVAILABLE,
            "kleidiai": FeatureStatus.UNKNOWN,
            "hugepages": FeatureStatus.UNKNOWN,
        }
        machine = platform.machine().lower()
        if machine in {"aarch64", "arm64"}:
            features["arm"] = FeatureStatus.AVAILABLE
        elif machine in {"x86_64", "amd64"}:
            features["arm"] = FeatureStatus.UNAVAILABLE

        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            text = cpuinfo.read_text(encoding="utf-8", errors="ignore").lower()
            for key, token in (
                ("sve2", "sve2"),
                ("sme", "sme"),
                ("dotprod", "asimddp"),
                ("i8mm", "i8mm"),
                ("mte", "mte"),
            ):
                features[key] = (
                    FeatureStatus.AVAILABLE
                    if token in text
                    else FeatureStatus.UNAVAILABLE
                )
        if os.getenv("NSA_DIPA_KLEIDIAI", ""):
            features["kleidiai"] = FeatureStatus.AVAILABLE
        return features
