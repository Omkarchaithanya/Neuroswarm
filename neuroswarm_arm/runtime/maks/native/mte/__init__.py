"""ARM Memory Tagging Extension — detection, syscalls, tag fault hook."""

from __future__ import annotations

import ctypes
import ctypes.util
import platform
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Linux uapi constants (asm/hwcap.h, linux/prctl.h, asm-generic/siginfo.h)
AT_HWCAP2 = 26
HWCAP2_MTE = 1 << 18

PR_SET_TAGGED_ADDR_CTRL = 55
PR_MTE_TCF_SYNC = 2

PROT_READ = 0x1
PROT_WRITE = 0x2
PROT_MTE = 0x20

MAP_PRIVATE = 0x02
MAP_ANONYMOUS = 0x20

SEGV_MTESERR = 9

SA_SIGINFO = 0x04
SIGSEGV = 11

_GRANULE = 16

# Logical tag bookkeeping when inline STG asm is unavailable.
_tag_by_ptr: dict[int, int] = {}
_fault_registry: Callable[[int], tuple[str, str, int] | None] | None = None
_handler_installed = False


def _libc() -> Any:
    name = ctypes.util.find_library("c")
    if not name:
        raise OSError("libc not found")
    libc = ctypes.CDLL(name, use_errno=True)
    return libc


def _cpuinfo_has_mte() -> bool:
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return False
    text = cpuinfo.read_text(encoding="utf-8", errors="ignore").lower()
    return bool(re.search(r"\bmte\b", text))


def _hwcap2_has_mte() -> bool:
    if platform.machine().lower() not in {"aarch64", "arm64"}:
        return False
    try:
        libc = _libc()
        getauxval = libc.getauxval
        getauxval.argtypes = [ctypes.c_ulong]
        getauxval.restype = ctypes.c_ulong
        hwcap2 = int(getauxval(AT_HWCAP2))
        return bool(hwcap2 & HWCAP2_MTE)
    except Exception:
        return False


def _kernel_advertises_mte() -> bool:
    try:
        libc = _libc()
        prctl = libc.prctl
        prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        prctl.restype = ctypes.c_int
        rc = prctl(PR_SET_TAGGED_ADDR_CTRL, PR_MTE_TCF_SYNC, 0, 0, 0)
        return rc == 0
    except Exception:
        return False


def detect_mte_support() -> bool:
    """Return True only when cpuinfo, HWCAP2, and kernel MTE are all present."""
    if sys.platform != "linux":
        return False
    if not _cpuinfo_has_mte():
        return False
    if not _hwcap2_has_mte():
        return False
    if not _kernel_advertises_mte():
        return False
    return True


AVAILABLE = detect_mte_support()


def align_granule(size: int) -> int:
    return (size + _GRANULE - 1) & ~(_GRANULE - 1)


def enable_mte_sync() -> None:
    """Enable synchronous MTE tag checking for the calling thread."""
    libc = _libc()
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    rc = prctl(PR_SET_TAGGED_ADDR_CTRL, PR_MTE_TCF_SYNC, 0, 0, 0)
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"prctl(PR_SET_TAGGED_ADDR_CTRL) failed: errno={err}")


def mte_mmap(size: int) -> tuple[int, int]:
    """Map anonymous tagged memory; returns (ptr, aligned_size)."""
    aligned = align_granule(size)
    libc = _libc()
    mmap_fn = libc.mmap
    mmap_fn.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_long,
    ]
    mmap_fn.restype = ctypes.c_void_p
    prot = PROT_READ | PROT_WRITE | PROT_MTE
    flags = MAP_PRIVATE | MAP_ANONYMOUS
    ptr = mmap_fn(None, aligned, prot, flags, -1, 0)
    if ptr is None or int(ptr) == -1:
        err = ctypes.get_errno()
        raise OSError(err, f"mmap(PROT_MTE) failed: errno={err}")
    return int(ptr), aligned


def mte_promote(addr: int, size: int) -> None:
    """Promote an existing mapping to include PROT_MTE."""
    aligned = align_granule(size)
    libc = _libc()
    mprotect = libc.mprotect
    mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    mprotect.restype = ctypes.c_int
    prot = PROT_READ | PROT_WRITE | PROT_MTE
    rc = mprotect(ctypes.c_void_p(addr), aligned, prot)
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"mprotect(PROT_MTE) failed: errno={err}")


def mte_munmap(addr: int, size: int) -> None:
    aligned = align_granule(size)
    libc = _libc()
    munmap = libc.munmap
    munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    munmap.restype = ctypes.c_int
    rc = munmap(ctypes.c_void_p(addr), aligned)
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"munmap failed: errno={err}")
    _tag_by_ptr.pop(addr, None)


def stg_tag(ptr: int, tag: int) -> None:
    """STG-equivalent: record logical tag and invoke tag_share bookkeeping."""
    if tag < 1 or tag > 15:
        raise ValueError(f"MTE tag must be 1..15, got {tag}")
    _tag_by_ptr[ptr] = tag
    tag_share(ptr, tag)


def tag_share(ptr: int, tag: int) -> None:
    """Grant foreign read via tag (bookkeeping until asm STG is wired)."""
    _tag_by_ptr[ptr] = tag


def read_foreign(ptr: int, tag: int) -> bytes:
    """Read tagged region; raises KVPermissionError if tag mismatches."""
    from neuroswarm_arm.runtime.maks.exceptions import KVPermissionError

    expected = _tag_by_ptr.get(ptr)
    if expected is not None and expected != tag:
        raise KVPermissionError(f"MTE tag mismatch ptr=0x{ptr:x} expected={expected} got={tag}")
    libc = _libc()
    # Caller must know size; this helper reads one granule for interface compat.
    buf = (ctypes.c_char * _GRANULE).from_address(ptr)
    return bytes(buf)


def tag_for_ptr(ptr: int) -> int | None:
    return _tag_by_ptr.get(ptr)


def _extract_tag_from_addr(addr: int) -> int:
    """Top 4 bits of address encode MTE tag on AArch64."""
    return (addr >> 56) & 0xF


def install_tag_fault_handler(
    registry: Callable[[int], tuple[str, str, int] | None],
) -> None:
    """Install SIGSEGV handler for SEGV_MTESERR tag faults."""
    global _fault_registry, _handler_installed
    if sys.platform != "linux" or not AVAILABLE:
        return
    if _handler_installed:
        _fault_registry = registry
        return

    from neuroswarm_arm.runtime.maks.exceptions import KVPermissionError

    _fault_registry = registry

    class _siginfo_t(ctypes.Structure):
        _fields_ = [
            ("si_signo", ctypes.c_int),
            ("si_errno", ctypes.c_int),
            ("si_code", ctypes.c_int),
            ("si_addr", ctypes.c_void_p),
        ]

    class _sigaction_t(ctypes.Structure):
        _fields_ = [
            ("sa_handler", ctypes.c_void_p),
            ("sa_mask", ctypes.c_ulong),
            ("sa_flags", ctypes.c_int),
            ("sa_restorer", ctypes.c_void_p),
        ]

    SA_HANDLER = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(_siginfo_t), ctypes.c_void_p)

    def _handler(signum: int, info: ctypes.POINTER(_siginfo_t), _context: ctypes.c_void_p) -> None:
        if info.contents.si_code != SEGV_MTESERR:
            return
        addr = int(info.contents.si_addr or 0)
        if _fault_registry is None:
            return
        meta = _fault_registry(addr)
        if meta is None:
            return
        _kv_id, session_id, expected_tag = meta
        actual_tag = _extract_tag_from_addr(addr)
        if actual_tag != expected_tag:
            raise KVPermissionError(
                f"MTE tag fault kv={_kv_id} session={session_id} "
                f"expected={expected_tag} actual={actual_tag}"
            )

    libc = _libc()
    sigaction = libc.sigaction
    sigaction.argtypes = [ctypes.c_int, ctypes.POINTER(_sigaction_t), ctypes.POINTER(_sigaction_t)]
    sigaction.restype = ctypes.c_int

    handler_cb = SA_HANDLER(_handler)
    act = _sigaction_t()
    act.sa_handler = ctypes.cast(handler_cb, ctypes.c_void_p).value
    act.sa_flags = SA_SIGINFO
    rc = sigaction(SIGSEGV, ctypes.byref(act), None)
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"sigaction(SIGSEGV) failed: errno={err}")

    # Keep reference alive
    install_tag_fault_handler._handler_ref = handler_cb  # type: ignore[attr-defined]
    _handler_installed = True
