"""HardwareProfiler — Axion-safe capability detection."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from ..models import HardwareCapabilities

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]


class HardwareProfiler:
    """Detect ARM features without requiring MTE/CXL/NUMA."""

    def __init__(self, dipa_features: dict[str, Any] | None = None) -> None:
        self._dipa_features = dict(dipa_features or {})

    def profile(self) -> HardwareCapabilities:
        features = self._cpu_features()
        cores = os.cpu_count() or 1
        ram = 0
        load = 0.0
        if psutil is not None:
            try:
                ram = int(psutil.virtual_memory().available)
                load = float(psutil.cpu_percent(interval=0.0)) / 100.0
            except Exception:
                pass
        if ram <= 0:
            ram = self._meminfo_available()

        numa = self._numa_nodes()
        omp = int(os.getenv("OMP_NUM_THREADS", str(max(1, cores // 2))) or max(1, cores // 2))

        # Merge DIPA FeatureDetector statuses when provided
        for key in ("sve2", "i8mm", "dotprod", "kleidiai", "hugepages", "mte", "cxl"):
            if key in self._dipa_features:
                val = self._dipa_features[key]
                features[key] = getattr(val, "value", str(val))

        return HardwareCapabilities(
            arch=platform.machine(),
            cpu_cores=cores,
            available_ram_bytes=ram,
            l3_cache_bytes=self._l3_cache_bytes(),
            memory_bandwidth_gbps=0.0,
            numa_nodes=numa,
            openmp_threads=omp,
            cpu_load=load,
            thermal_throttling=False,
            sve2=features.get("sve2", "UNKNOWN"),
            i8mm=features.get("i8mm", "UNKNOWN"),
            dotprod=features.get("dotprod", "UNKNOWN"),
            bf16=features.get("bf16", "UNKNOWN"),
            kleidiai=features.get("kleidiai", "UNKNOWN"),
            hugepages=features.get("hugepages", "UNKNOWN"),
            thp=features.get("thp", "UNKNOWN"),
            mte=features.get("mte", "UNAVAILABLE"),
            cxl=features.get("cxl", "UNAVAILABLE"),
            details={"source": "aqr.hardware"},
        )

    def _cpu_features(self) -> dict[str, str]:
        out = {
            "sve2": "UNKNOWN",
            "i8mm": "UNKNOWN",
            "dotprod": "UNKNOWN",
            "bf16": "UNKNOWN",
            "kleidiai": "UNKNOWN",
            "hugepages": "UNKNOWN",
            "thp": "UNKNOWN",
            "mte": "UNAVAILABLE",
            "cxl": "UNAVAILABLE",
        }
        machine = platform.machine().lower()
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            text = cpuinfo.read_text(encoding="utf-8", errors="ignore").lower()
            mapping = {
                "sve2": "sve2",
                "i8mm": "i8mm",
                "dotprod": "asimddp",
                "bf16": "bf16",
                "mte": "mte",
            }
            for key, token in mapping.items():
                out[key] = "AVAILABLE" if token in text else "UNAVAILABLE"
        elif machine in {"aarch64", "arm64"}:
            # Windows/macOS ARM — unknown features
            pass
        else:
            for k in ("sve2", "i8mm", "dotprod", "bf16"):
                out[k] = "UNAVAILABLE"

        if os.getenv("NSA_DIPA_KLEIDIAI", "") or os.getenv("NSA_AQR_KLEIDIAI", ""):
            out["kleidiai"] = "AVAILABLE"

        hp = Path("/sys/kernel/mm/hugepages")
        if hp.exists():
            out["hugepages"] = "AVAILABLE"
        thp = Path("/sys/kernel/mm/transparent_hugepage/enabled")
        if thp.exists():
            try:
                content = thp.read_text(encoding="utf-8")
                out["thp"] = "AVAILABLE" if "[always]" in content or "[madvise]" in content else "UNAVAILABLE"
            except Exception:
                out["thp"] = "UNKNOWN"
        return out

    @staticmethod
    def _numa_nodes() -> int:
        base = Path("/sys/devices/system/node")
        if not base.exists():
            return 1
        nodes = list(base.glob("node[0-9]*"))
        return max(1, len(nodes))

    @staticmethod
    def _meminfo_available() -> int:
        path = Path("/proc/meminfo")
        if not path.exists():
            return 8 * 1024 * 1024 * 1024
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb * 1024
        except Exception:
            pass
        return 8 * 1024 * 1024 * 1024

    @staticmethod
    def _l3_cache_bytes() -> int:
        # Best-effort on Linux
        for path in Path("/sys/devices/system/cpu").glob("cpu0/cache/index*/size"):
            try:
                level = path.parent / "level"
                if level.exists() and level.read_text().strip() == "3":
                    raw = path.read_text().strip().upper()
                    if raw.endswith("K"):
                        return int(raw[:-1]) * 1024
                    if raw.endswith("M"):
                        return int(raw[:-1]) * 1024 * 1024
            except Exception:
                continue
        return 0
