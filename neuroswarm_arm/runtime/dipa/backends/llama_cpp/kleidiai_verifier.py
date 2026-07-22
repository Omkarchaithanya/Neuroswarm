"""KleidiAI verifier — CPU feature gate + llama.cpp kernel log evidence."""

from __future__ import annotations

import ctypes
import ctypes.util
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path

KLEIDIAI_PATTERN = re.compile(
    r"load_tensors:\s*CPU_KLEIDIAI\s+model\s+buffer\s+size",
    re.IGNORECASE,
)

KERNEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    KLEIDIAI_PATTERN,
    re.compile(r"kai_matmul", re.IGNORECASE),
    re.compile(r"matmul_clamp_qai8dxp", re.IGNORECASE),
    re.compile(r"ggml-cpu-aarch64", re.IGNORECASE),
)

# Linux aarch64 hwcap bits (from kernel uapi asm/hwcap.h)
_HWCAP_ASIMDDP = 1 << 20
_HWCAP2_SVE2 = 1 << 1
_HWCAP2_I8MM = 1 << 13


@dataclass(slots=True)
class CpuFeatureResult:
    sve2: bool = False
    i8mm: bool = False
    asimddp: bool = False
    source: str = "unknown"

    @property
    def ok(self) -> bool:
        return self.sve2 and self.i8mm and self.asimddp


@dataclass(slots=True)
class KleidiaiVerifyResult:
    ok: bool
    cpu_ok: bool = False
    kernel_ok: bool = False
    matched_line: str = ""
    matched_kernel: str = ""
    require: bool = False
    message: str = ""
    cpu_features: CpuFeatureResult = field(default_factory=CpuFeatureResult)


def _cpu_gate_enforced() -> bool:
    """Enforce CPU feature gate only on Linux ARM hosts."""
    if Path("/proc/cpuinfo").exists():
        return True
    return platform.machine().lower() in {"aarch64", "arm64"}


def probe_cpu_features() -> CpuFeatureResult:
    """Check Axion-class ARM features via /proc/cpuinfo with getauxval fallback."""
    result = CpuFeatureResult()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        text = cpuinfo.read_text(encoding="utf-8", errors="ignore").lower()
        result.sve2 = "sve2" in text
        result.i8mm = "i8mm" in text
        result.asimddp = "asimddp" in text
        result.source = "cpuinfo"
        if result.ok:
            return result

    if platform.machine().lower() in {"aarch64", "arm64"}:
        aux = _getauxval_features()
        result.sve2 = result.sve2 or aux.get("sve2", False)
        result.i8mm = result.i8mm or aux.get("i8mm", False)
        result.asimddp = result.asimddp or aux.get("asimddp", False)
        if aux:
            result.source = "getauxval" if result.source == "unknown" else f"{result.source}+getauxval"

    return result


def _getauxval_features() -> dict[str, bool]:
    out: dict[str, bool] = {}
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        getauxval = libc.getauxval
        getauxval.argtypes = [ctypes.c_ulong]
        getauxval.restype = ctypes.c_ulong
    except Exception:
        return out

    # AT_HWCAP=16, AT_HWCAP2=26
    try:
        hwcap = int(getauxval(16))
        hwcap2 = int(getauxval(26))
        out["asimddp"] = bool(hwcap & _HWCAP_ASIMDDP)
        out["sve2"] = bool(hwcap2 & _HWCAP2_SVE2)
        out["i8mm"] = bool(hwcap2 & _HWCAP2_I8MM)
    except Exception:
        pass
    return out


def _match_kernel_line(text: str) -> tuple[bool, str, str]:
    for pattern in KERNEL_PATTERNS:
        if pattern.search(text):
            return True, text, pattern.pattern
    return False, "", ""


class KleidiaiVerifier:
    """Scrape llama-server logs for KleidiAI activation evidence."""

    def __init__(self, *, require: bool = False) -> None:
        self.require = require
        self._buffer: list[str] = []
        self._matched: str = ""
        self._matched_kernel: str = ""
        self._cpu = probe_cpu_features()

    @property
    def cpu_features(self) -> CpuFeatureResult:
        return self._cpu

    def feed(self, line: str) -> bool:
        text = line.rstrip("\n")
        self._buffer.append(text)
        if len(self._buffer) > 5000:
            self._buffer = self._buffer[-2500:]
        matched, line_text, kernel = _match_kernel_line(text)
        if matched:
            self._matched = line_text
            self._matched_kernel = kernel
            return True
        return False

    def feed_many(self, text: str) -> bool:
        ok = False
        for line in text.splitlines():
            if self.feed(line):
                ok = True
        return ok

    def result(self) -> KleidiaiVerifyResult:
        kernel_ok = bool(self._matched)
        cpu_ok = self._cpu.ok or not _cpu_gate_enforced()

        if kernel_ok and cpu_ok:
            return KleidiaiVerifyResult(
                ok=True,
                cpu_ok=True,
                kernel_ok=True,
                matched_line=self._matched,
                matched_kernel=self._matched_kernel,
                require=self.require,
                message="KleidiAI active",
                cpu_features=self._cpu,
            )

        if kernel_ok and not self.require:
            return KleidiaiVerifyResult(
                ok=True,
                cpu_ok=cpu_ok,
                kernel_ok=True,
                matched_line=self._matched,
                matched_kernel=self._matched_kernel,
                require=False,
                message="KleidiAI kernel detected (CPU features unverified)",
                cpu_features=self._cpu,
            )

        if self.require:
            if _cpu_gate_enforced() and not self._cpu.ok:
                missing = []
                if not self._cpu.sve2:
                    missing.append("sve2")
                if not self._cpu.i8mm:
                    missing.append("i8mm")
                if not self._cpu.asimddp:
                    missing.append("asimddp")
                return KleidiaiVerifyResult(
                    ok=False,
                    cpu_ok=False,
                    kernel_ok=kernel_ok,
                    require=True,
                    message=f"CPU features missing: {', '.join(missing)}",
                    cpu_features=self._cpu,
                )
            return KleidiaiVerifyResult(
                ok=False,
                cpu_ok=True,
                kernel_ok=False,
                require=True,
                message="KleidiAI kernel names absent from llama-server logs",
                cpu_features=self._cpu,
            )

        return KleidiaiVerifyResult(
            ok=True,
            cpu_ok=cpu_ok,
            kernel_ok=kernel_ok,
            require=False,
            message="KleidiAI not verified (NSA_REQUIRE_KLEIDIAI unset)",
            cpu_features=self._cpu,
        )

    def assert_ready(self) -> None:
        res = self.result()
        if self.require and not res.ok:
            raise RuntimeError(res.message)
        if self.require and not res.kernel_ok:
            raise RuntimeError(res.message)


def validate_kleidiai(
    log_text: str = "",
    *,
    require: bool = False,
    cpu_features: CpuFeatureResult | None = None,
) -> KleidiaiVerifyResult:
    """Validate KleidiAI from log text; raise when require=True and evidence absent."""
    verifier = KleidiaiVerifier(require=require)
    if cpu_features is not None:
        verifier._cpu = cpu_features
    if log_text:
        verifier.feed_many(log_text)
    result = verifier.result()
    if require and not result.kernel_ok:
        raise RuntimeError(result.message)
    if require and _cpu_gate_enforced() and cpu_features is not None and not cpu_features.ok:
        raise RuntimeError(result.message)
    return result
