"""ARM / Axion hardware adapters — dual-mode locality (NUMA vs cache-aware)."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Any, Mapping


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _cores_bitmap(cores: list[int]) -> int:
    bits = 0
    for c in cores:
        if 0 <= int(c) < 63:
            bits |= 1 << int(c)
    return bits


@dataclass(slots=True)
class ArmPlacement:
    draft_numa_node: int = 0
    verify_numa_node: int = 0
    numa_available: bool = False
    locality: float = 1.0
    kleidiai: bool = False
    message: str = "Axion single-UMA cache-aware affinity"
    locality_mode: str = "cache_aware"
    draft_cores: list[int] = field(default_factory=list)
    verify_cores: list[int] = field(default_factory=list)
    # Apple: 1=E-core, 2=P-core; Arm: packed cores bitmap
    draft_affinity_tag: int = 0
    verify_affinity_tag: int = 0
    pcore_count: int = 0
    ecore_count: int = 0


class ArmRuntimeAdapter:
    """Best-effort topology placement: NUMA when multi-node, else core partitions."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict((config or {}).get("arm") or config or {})
        self._placement = ArmPlacement()

    def detect_apple_silicon(self) -> ArmPlacement | None:
        """P/E-core split via sysctl perflevels. None if not Darwin / probe fail."""
        if platform.system() != "Darwin":
            return None
        try:
            p_raw = subprocess.check_output(
                ["sysctl", "-n", "hw.perflevel0.logicalcpu"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            e_raw = subprocess.check_output(
                ["sysctl", "-n", "hw.perflevel1.logicalcpu"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            pcores = max(0, int(p_raw))
            ecores = max(0, int(e_raw))
        except (OSError, subprocess.CalledProcessError, ValueError):
            return None
        if pcores + ecores <= 0:
            return None

        # Logical layout: P-cores first, then E-cores (Apple Silicon convention).
        p_list = list(range(pcores))
        e_list = list(range(pcores, pcores + ecores))
        ecore_for_draft = _env_bool("NSA_APPLE_ECORE_FOR_DRAFT", True)
        if ecore_for_draft and e_list:
            draft, verify = e_list, p_list or e_list
            draft_tag, verify_tag = 1, 2  # E, P
        else:
            draft, verify = p_list or e_list, e_list or p_list
            draft_tag, verify_tag = 2, 1

        self._placement = ArmPlacement(
            draft_numa_node=0,
            verify_numa_node=0,
            numa_available=False,
            locality=1.0,
            kleidiai=False,
            message="Apple Silicon P/E-core draft/verify affinity",
            locality_mode="apple_perflevel",
            draft_cores=list(draft),
            verify_cores=list(verify),
            draft_affinity_tag=draft_tag,
            verify_affinity_tag=verify_tag,
            pcore_count=pcores,
            ecore_count=ecores,
        )
        return self._placement

    def detect(self, hardware: Any | None = None) -> ArmPlacement:
        if not _env_bool("NSA_DRAFT_VERIFY_AFFINITY", True):
            self._placement = ArmPlacement(message="draft/verify affinity disabled")
            return self._placement

        apple = self.detect_apple_silicon()
        if apple is not None:
            return apple

        from neuroswarm_arm.runtime.haoe.topology.locality_scheduler import (
            resolve_locality_plan,
        )
        from neuroswarm_arm.runtime.haoe.topology.cpu_topology import read_online_cpus

        numa_nodes = 1
        kleidiai = False
        online = read_online_cpus()
        if hardware is not None:
            numa_nodes = int(getattr(hardware, "numa_nodes", 1) or 1)
            feats = getattr(hardware, "features", None) or {}
            if isinstance(feats, dict):
                kleidiai = bool(feats.get("kleidiai") or feats.get("i8mm"))
            hw_cores = getattr(hardware, "cores", None) or getattr(hardware, "logical_cpus", None)
            if hw_cores:
                online = [int(c) for c in hw_cores]

        multi = numa_nodes > 1 and bool(self.config.get("numa_aware", True))
        plan = resolve_locality_plan(
            numa_nodes=numa_nodes, online_cores=online, multi_node=multi
        )
        draft = plan.cores_for("draft")
        verify = plan.cores_for("verify")

        if multi and plan.mode == "numa_aware":
            self._placement = ArmPlacement(
                draft_numa_node=0,
                verify_numa_node=1,
                numa_available=True,
                locality=1.0,
                kleidiai=kleidiai,
                message="multi-NUMA placement (numactl)",
                locality_mode="numa_aware",
                draft_cores=draft,
                verify_cores=verify,
                draft_affinity_tag=_cores_bitmap(draft),
                verify_affinity_tag=_cores_bitmap(verify),
            )
        else:
            draft_cores = draft or (online[:2] if online else [0])
            verify_cores = verify or (online[2:] if len(online) > 2 else online)
            self._placement = ArmPlacement(
                draft_numa_node=0,
                verify_numa_node=0,
                numa_available=False,
                locality=1.0,
                kleidiai=kleidiai,
                message=plan.reason or "single-UMA cache-aware CPU affinity",
                locality_mode=plan.mode,
                draft_cores=draft_cores,
                verify_cores=verify_cores,
                draft_affinity_tag=_cores_bitmap(draft_cores),
                verify_affinity_tag=_cores_bitmap(verify_cores),
            )
        return self._placement

    @property
    def placement(self) -> ArmPlacement:
        return self._placement

    @property
    def pcore_count(self) -> int:
        return int(self._placement.pcore_count)

    @property
    def ecore_count(self) -> int:
        return int(self._placement.ecore_count)

    def pin_current_thread(self, pool: str = "draft") -> bool:
        """Best-effort pin to draft or verify core partition."""
        if pool == "draft" and not self.config.get("pin_draft_pool", True):
            return False
        if pool == "verify" and not self.config.get("pin_verify_pool", True):
            return False
        try:
            if not self._placement.draft_cores and not self._placement.verify_cores:
                self.detect()
            cores = (
                self._placement.draft_cores
                if pool == "draft"
                else self._placement.verify_cores
            )
            if not cores:
                cores = [0]
            return _apply_affinity(set(int(c) for c in cores))
        except (OSError, AttributeError, PermissionError):
            return False


def _apply_affinity(cores: set[int]) -> bool:
    """Linux sched_setaffinity; Apple thread_policy_set best-effort."""
    if not cores:
        return False
    if platform.system() == "Darwin":
        return _apple_thread_affinity(cores)
    try:
        import os

        if not hasattr(os, "sched_setaffinity"):
            return False
        os.sched_setaffinity(0, cores)
        return True
    except (OSError, AttributeError, PermissionError):
        return False


def _apple_thread_affinity(cores: set[int]) -> bool:
    """Best-effort mach thread_policy_set (no-op if ctypes/mach unavailable)."""
    try:
        import ctypes
        import ctypes.util

        lib = ctypes.util.find_library("System") or "/usr/lib/libSystem.dylib"
        libc = ctypes.CDLL(lib, use_errno=True)
        # THREAD_AFFINITY_POLICY = 4; policy is affinity_tag (integer).
        # Map first core id into affinity tag; full cpuset needs QoS APIs.
        tag = min(cores) + 1
        policy = ctypes.c_uint32(tag)
        count = ctypes.c_uint32(1)
        # pthread_threadid_np / thread_policy_set — best effort; return False on miss.
        if not hasattr(libc, "thread_policy_set"):
            return False
        # mach_thread_self
        if not hasattr(libc, "mach_thread_self"):
            return False
        thread = libc.mach_thread_self()
        # THREAD_AFFINITY_POLICY = 4
        rc = libc.thread_policy_set(thread, 4, ctypes.byref(policy), count)
        return int(rc) == 0
    except Exception:  # noqa: BLE001
        return False


class PerformixHook:
    """Observation sink for ARM Performix / EvolutionLoop (no ownership)."""

    def __init__(self) -> None:
        self.last: dict[str, float] = {}

    def record(self, fields: Mapping[str, float]) -> None:
        self.last = {str(k): float(v) for k, v in fields.items()}
