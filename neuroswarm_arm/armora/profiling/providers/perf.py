"""Linux perf_events provider (optional; Axion-honest when unavailable).

Attach target PID via ``NSA_PERF_PID`` (Kleidi llama-server) when set; otherwise
profiles the current process (gateway). Arm / SVE PMU events are probed once and
never hard-fail the provider. When hardware PMU is absent, software events are used.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from ..schemas import CapabilityState, MetricBatch, ProfileSessionContext, ProviderCapabilities
from .base import BaseProfilerProvider, detect_cpu_flags, empty_batch, is_linux, samples_from_mapping, which_binary

logger = logging.getLogger(__name__)

_BASE_EVENTS = (
    "cycles",
    "instructions",
    "cache-misses",
    "cache-references",
    "branch-misses",
)
_SOFT_EVENTS = (
    "task-clock",
    "cpu-clock",
    "context-switches",
    "page-faults",
)


def _resolve_target_pid() -> int:
    raw = (os.environ.get("NSA_PERF_PID") or os.environ.get("PERF_PID") or "").strip()
    if raw.isdigit():
        return int(raw)
    return os.getpid()


def _hardware_pmu_present() -> bool:
    devices = Path("/sys/bus/event_source/devices")
    return devices.exists() and any(devices.glob("armv8_pmuv3*"))


def _discover_arm_events(perf_bin: str) -> list[str]:
    """Best-effort list of SVE/NEON/i8mm events from ``perf list``."""
    try:
        out = subprocess.run(
            [perf_bin, "list"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return []
    blob = f"{out.stdout}\n{out.stderr}"
    found: list[str] = []
    for m in re.finditer(
        r"\b([a-z0-9_./-]*(?:sve2?|i8mm|neon|ase_inst|sve_inst)[a-z0-9_./-]*)\b",
        blob,
        re.I,
    ):
        ev = m.group(1)
        if re.search(r"(?:release|lease|phase|cleanup)", ev, re.I):
            continue
        if ev not in found and ":" not in ev.split("/")[0]:
            found.append(ev)
        if len(found) >= 8:
            break
    usable: list[str] = []
    for ev in found:
        try:
            r = subprocess.run(
                [perf_bin, "stat", "-e", ev, "--", "true"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if r.returncode == 0 and "not supported" not in (r.stderr or "").lower():
                usable.append(ev)
        except Exception:
            continue
    return usable


def _parse_perf_stat(stderr: str) -> dict[str, float]:
    out: dict[str, float] = {}
    patterns = {
        "cycles": r"([\d,]+)\s+cycles",
        "instructions": r"([\d,]+)\s+instructions",
        "cache_misses": r"([\d,]+)\s+cache-misses",
        "cache_references": r"([\d,]+)\s+cache-references",
        "branch_misses": r"([\d,]+)\s+branch-misses",
        "task_clock": r"([\d,.]+)\s+task-clock",
        "cpu_clock": r"([\d,.]+)\s+cpu-clock",
        "context_switches": r"([\d,]+)\s+context-switches",
        "page_faults": r"([\d,]+)\s+page-faults",
    }
    for key, pat in patterns.items():
        m = re.search(pat, stderr, re.I)
        if m:
            try:
                out[key] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    for m in re.finditer(r"([\d,]+)\s+([a-zA-Z0-9_./-]+)", stderr):
        name = m.group(2).strip().rstrip(",")
        if any(tok in name.lower() for tok in ("sve", "i8mm", "neon", "ase_inst", "sve_inst")):
            try:
                out[f"arm_{re.sub(r'[^a-z0-9_]+', '_', name.lower())}"] = float(
                    m.group(1).replace(",", "")
                )
            except ValueError:
                pass
    return out


class PerfProfilerProvider(BaseProfilerProvider):
    name = "perf"

    def __init__(self) -> None:
        super().__init__()
        self._perf = which_binary("perf")
        self._arm_events: list[str] | None = None
        self._target_pid = _resolve_target_pid()

    def _arm_event_list(self) -> list[str]:
        if self._arm_events is None:
            self._arm_events = (
                _discover_arm_events(self._perf) if self._perf and _hardware_pmu_present() else []
            )
        return self._arm_events

    def capabilities(self) -> ProviderCapabilities:
        flags = detect_cpu_flags()
        linux = is_linux()
        hw = _hardware_pmu_present() if linux else False
        arm = self._arm_event_list() if self._perf and linux and hw else []
        state = CapabilityState.AVAILABLE if (linux and self._perf) else CapabilityState.UNAVAILABLE
        reasons: list[str] = []
        if not linux:
            reasons.append("not_linux")
        if not self._perf:
            reasons.append("perf_missing")
        if linux and self._perf and not hw:
            reasons.append("hardware_pmu_absent_software_fallback")
        return ProviderCapabilities(
            name=self.name,
            state=state,
            features={
                "perf_stat": bool(self._perf),
                "target_pid": self._target_pid,
                "sve_cpu_flag": "sve" in flags or "sve2" in flags,
                "sve_events_available": bool(arm),
                "arm_event_count": len(arm),
                "hardware_pmu_available": hw,
            },
            reasons=reasons,
        )

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        if cfg.get("pid") is not None:
            try:
                self._target_pid = int(cfg["pid"])
            except (TypeError, ValueError):
                pass
        else:
            self._target_pid = _resolve_target_pid()
        self._initialized = True

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        if not self._perf or not is_linux():
            return empty_batch(self.name, session)
        self._target_pid = _resolve_target_pid()
        duration_ms = max(50, int(getattr(session, "sample_interval_ms", 200) or 200))
        sleep_s = max(0.05, duration_ms / 1000.0)
        try:
            hw_ok = _hardware_pmu_present()
            events = (
                list(_BASE_EVENTS) + self._arm_event_list() if hw_ok else list(_SOFT_EVENTS)
            )
            event_csv = ",".join(events)
            cmd = [
                self._perf,
                "stat",
                "-e",
                event_csv,
                "-p",
                str(self._target_pid),
                "--",
                "sleep",
                f"{sleep_s:.3f}",
            ]
            runners: list[list[str]] = [cmd]
            if which_binary("sudo"):
                runners.insert(0, ["sudo", "-n", *cmd])
            parsed: dict[str, float] = {}
            for runner in runners:
                proc = subprocess.run(
                    runner,
                    capture_output=True,
                    text=True,
                    timeout=max(5.0, sleep_s + 3.0),
                    check=False,
                )
                last_err = proc.stderr or ""
                if "not supported" in last_err.lower():
                    soft_cmd = (
                        ["sudo", "-n", self._perf]
                        if runner[0] == "sudo"
                        else [self._perf]
                    ) + [
                        "stat",
                        "-e",
                        ",".join(_SOFT_EVENTS),
                        "-p",
                        str(self._target_pid),
                        "--",
                        "sleep",
                        f"{sleep_s:.3f}",
                    ]
                    proc = subprocess.run(
                        soft_cmd,
                        capture_output=True,
                        text=True,
                        timeout=max(5.0, sleep_s + 3.0),
                        check=False,
                    )
                    last_err = proc.stderr or ""
                    hw_ok = False
                parsed = _parse_perf_stat(last_err)
                if parsed.get("cycles") or parsed.get("instructions") or parsed.get("task_clock"):
                    break
            cycles = float(parsed.get("cycles") or 0.0)
            instr = float(parsed.get("instructions") or 0.0)
            ipc = (instr / cycles) if cycles > 0 else 0.0
            sve_keys = [k for k in parsed if "sve" in k.lower()]
            sve_sum = sum(float(parsed[k]) for k in sve_keys)
            values = {
                "hardware.cycles": cycles,
                "hardware.instructions": instr,
                "hardware.ipc": ipc,
                "hardware.cache_misses": float(parsed.get("cache_misses") or 0.0),
                "hardware.cache_references": float(parsed.get("cache_references") or 0.0),
                "hardware.branch_misses": float(parsed.get("branch_misses") or 0.0),
                "hardware.sve_inst_retired": sve_sum,
                "hardware.sve_events_available": 1.0 if (hw_ok and self._arm_event_list()) else 0.0,
                "hardware.pmu_available": 1.0 if hw_ok else 0.0,
                "hardware.task_clock": float(parsed.get("task_clock") or 0.0),
                "hardware.cpu_clock": float(parsed.get("cpu_clock") or 0.0),
                "hardware.context_switches": float(parsed.get("context_switches") or 0.0),
                "hardware.target_pid": float(self._target_pid),
            }
            for k, v in parsed.items():
                if k.startswith("arm_"):
                    values[f"hardware.{k}"] = float(v)
            self._failures = 0
            return samples_from_mapping(self.name, session, values)
        except Exception as exc:
            self._failures += 1
            self._last_error = str(exc)
            logger.debug("perf sample failed: %s", exc)
            return empty_batch(self.name, session)

    def shutdown(self) -> None:
        self._initialized = False
