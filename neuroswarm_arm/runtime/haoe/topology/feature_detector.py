"""Hardware feature detection — Axion-safe, never raises on missing sysfs."""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..interfaces.types import FeatureStatus


_FEATURE_ALIASES = {
    "sve": "sve",
    "sve2": "sve2",
    "sme": "sme",
    "sme2": "sme2",
    "dotprod": "dotprod",
    "asimddp": "dotprod",
    "i8mm": "i8mm",
    "mte": "mte",
    "mte3": "mte",
    "bf16": "bf16",
    "asimd": "asimd",
    "neon": "asimd",
    "crc32": "crc32",
    "atomics": "lse",
    "lse": "lse",
}


@dataclass(slots=True)
class FeatureSet:
    features: dict[str, FeatureStatus] = field(default_factory=dict)
    flags_raw: set[str] = field(default_factory=set)
    arch: str = ""
    vendor: str = ""

    def status(self, name: str) -> FeatureStatus:
        return self.features.get(name.lower(), FeatureStatus.UNKNOWN)

    def to_dict(self) -> dict[str, str]:
        return {k: v.value for k, v in sorted(self.features.items())}


class FeatureDetector:
    """Parse /proc/cpuinfo + sysfs; degrade to UNKNOWN/UNAVAILABLE off-Linux."""

    TRACKED = (
        "sve",
        "sve2",
        "sme",
        "sme2",
        "dotprod",
        "i8mm",
        "mte",
        "bf16",
        "asimd",
        "cxl",
        "hugepages",
        "thp",
        "hyperthreading",
        "numa",
    )

    def detect(self) -> FeatureSet:
        arch = platform.machine().lower()
        flags = self._cpu_flags()
        features: dict[str, FeatureStatus] = {}

        for name in self.TRACKED:
            features[name] = FeatureStatus.UNAVAILABLE

        for flag in flags:
            canon = _FEATURE_ALIASES.get(flag.lower())
            if canon:
                features[canon] = FeatureStatus.AVAILABLE

        # CXL is not a CPU flag — probe sysfs / DAX placeholders.
        features["cxl"] = (
            FeatureStatus.AVAILABLE
            if self._path_exists("/sys/bus/cxl")
            else FeatureStatus.UNAVAILABLE
        )
        features["hugepages"] = (
            FeatureStatus.AVAILABLE
            if self._path_exists("/sys/kernel/mm/hugepages")
            else FeatureStatus.UNAVAILABLE
        )
        features["thp"] = self._thp_status()
        features["numa"] = (
            FeatureStatus.AVAILABLE
            if len(self._numa_nodes()) > 1
            else FeatureStatus.UNAVAILABLE
        )
        features["hyperthreading"] = self._smt_status()

        # On non-ARM, SVE family stays UNAVAILABLE (already set).
        if not arch.startswith(("arm", "aarch")):
            for k in ("sve", "sve2", "sme", "sme2", "i8mm", "mte"):
                if features.get(k) is FeatureStatus.UNKNOWN:
                    features[k] = FeatureStatus.UNAVAILABLE

        vendor = platform.processor() or ""
        return FeatureSet(features=features, flags_raw=flags, arch=arch, vendor=vendor)

    def _cpu_flags(self) -> set[str]:
        path = Path("/proc/cpuinfo")
        if not path.exists():
            return set()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return set()
        flags: set[str] = set()
        for line in text.splitlines():
            if line.lower().startswith(("features", "flags")):
                _, _, rest = line.partition(":")
                flags.update(rest.strip().split())
        return flags

    def _numa_nodes(self) -> list[int]:
        sysfs = Path("/sys/devices/system/node")
        if not sysfs.exists():
            return [0]
        nodes: list[int] = []
        try:
            for child in sorted(sysfs.iterdir()):
                name = child.name
                if name.startswith("node") and name[4:].isdigit():
                    nodes.append(int(name[4:]))
        except OSError:
            return [0]
        return nodes or [0]

    def _thp_status(self) -> FeatureStatus:
        path = Path("/sys/kernel/mm/transparent_hugepage/enabled")
        if not path.exists():
            return FeatureStatus.UNAVAILABLE
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return FeatureStatus.UNKNOWN
        # Format: [always] madvise never  OR  always [madvise] never
        if "[always]" in text or "[madvise]" in text:
            return FeatureStatus.AVAILABLE
        return FeatureStatus.UNAVAILABLE

    def _smt_status(self) -> FeatureStatus:
        path = Path("/sys/devices/system/cpu/smt/active")
        if path.exists():
            try:
                return (
                    FeatureStatus.AVAILABLE
                    if path.read_text(encoding="utf-8").strip() == "1"
                    else FeatureStatus.UNAVAILABLE
                )
            except OSError:
                return FeatureStatus.UNKNOWN
        # Heuristic: siblings > cores on Linux topology
        try:
            siblings = Path("/sys/devices/system/cpu/cpu0/topology/thread_siblings_list")
            if siblings.exists():
                text = siblings.read_text(encoding="utf-8").strip()
                ids = re.split(r"[-,]", text)
                if len([x for x in ids if x.isdigit()]) > 1:
                    return FeatureStatus.AVAILABLE
        except OSError:
            pass
        return FeatureStatus.UNAVAILABLE

    @staticmethod
    def _path_exists(path: str) -> bool:
        return Path(path).exists()


def parse_cpuinfo_features(text: str) -> set[str]:
    """Test helper: parse features from a cpuinfo fixture string."""
    flags: set[str] = set()
    for line in text.splitlines():
        if line.lower().startswith(("features", "flags")):
            _, _, rest = line.partition(":")
            flags.update(rest.strip().split())
    return flags
