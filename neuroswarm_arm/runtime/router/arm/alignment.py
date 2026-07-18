"""ARM memory alignment and feature detection helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
import platform
from typing import Any

import numpy as np


@dataclass(slots=True)
class ArmFeatures:
    arch: str
    is_arm64: bool
    neon: bool
    sve: bool
    sve2: bool
    numa_nodes: int
    huge_pages_hint: bool


def detect_arm_features() -> ArmFeatures:
    arch = platform.machine().lower()
    is_arm = arch in {"aarch64", "arm64", "armv8", "armv8l"}
    neon = is_arm
    sve = False
    sve2 = False
    if is_arm:
        try:
            if os.path.exists("/proc/cpuinfo"):
                cpuinfo = open("/proc/cpuinfo", encoding="utf-8", errors="ignore").read().lower()
                for line in cpuinfo.splitlines():
                    if "features" in line or line.strip().startswith("flags"):
                        tokens = set(line.split(":", 1)[-1].split())
                        sve = "sve" in tokens
                        sve2 = "sve2" in tokens
                        if sve or sve2:
                            break
                if not sve and not sve2:
                    sve2 = "sve2" in cpuinfo
                    sve = "sve" in cpuinfo or sve2
        except Exception:
            pass
        if os.getenv("NSA_ROUTER_FORCE_SVE2") == "1":
            sve = True
            sve2 = True
    numa = 1
    try:
        nodes = os.listdir("/sys/devices/system/node")
        numa = max(1, len([n for n in nodes if n.startswith("node")]))
    except Exception:
        numa = 1
    huge = os.getenv("NSA_ROUTER_HUGEPAGES", "0") not in {"0", "false", "False"}
    return ArmFeatures(
        arch=arch,
        is_arm64=is_arm,
        neon=neon,
        sve=sve,
        sve2=sve2,
        numa_nodes=numa,
        huge_pages_hint=huge,
    )


def aligned_float32(shape: tuple[int, ...], align: int = 64) -> np.ndarray:
    if not shape or shape[0] == 0:
        return np.zeros(shape, dtype=np.float32)
    nbytes = int(np.prod(shape)) * 4
    buf = np.empty(nbytes + align, dtype=np.uint8)
    addr = buf.ctypes.data
    offset = (align - (addr % align)) % align
    view = np.frombuffer(buf, dtype=np.float32, count=int(np.prod(shape)), offset=offset)
    arr = view.reshape(shape)
    arr.fill(0.0)
    return np.ascontiguousarray(arr)


def pin_current_thread(cores: list[int]) -> bool:
    if not cores:
        return False
    try:
        os.sched_setaffinity(0, set(cores))  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def hugepage_advice(path: str) -> dict[str, Any]:
    feats = detect_arm_features()
    return {
        "path": path,
        "huge_pages_requested": feats.huge_pages_hint,
        "supported": feats.is_arm64 and os.name == "posix",
        "note": "Axion: hugepage advice only; enable via OS config if available",
    }
