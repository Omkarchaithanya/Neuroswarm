"""eBPF / bpftrace provider — real sampling when NSA_EBPF_PROFILE=1.

Attaches short bpftrace uprobes to ggml/llama symbols on ``NSA_PERF_PID`` /
``NSA_EBPF_BINARY`` when available. Otherwise reports UNAVAILABLE with clear
reasons (no fake SVE/util zeros). ProfInfer is research-only and not vendored.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..schemas import CapabilityState, MetricBatch, ProfileSessionContext, ProviderCapabilities
from .base import BaseProfilerProvider, empty_batch, is_linux, samples_from_mapping, which_binary

logger = logging.getLogger(__name__)

_CANDIDATE_SYMS = (
    "ggml_graph_compute",
    "ggml_backend_sched_graph_compute",
    "llama_decode",
    "llama_encode",
    "ggml_backend_cpu_graph_compute",
)


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _target_pid() -> int | None:
    raw = (os.environ.get("NSA_PERF_PID") or os.environ.get("PERF_PID") or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _binary_path(pid: int | None) -> str | None:
    explicit = (os.environ.get("NSA_EBPF_BINARY") or "").strip()
    if explicit and Path(explicit).exists():
        return explicit
    if pid is None:
        return None
    try:
        return str(Path(f"/proc/{pid}/exe").resolve())
    except Exception:
        return None


def _discover_symbols(binary: str) -> list[str]:
    found: list[str] = []
    for cmd in (
        ["nm", "-D", binary],
        ["readelf", "-Ws", binary],
    ):
        if not which_binary(cmd[0]):
            continue
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        except Exception:
            continue
        names = set(out.stdout.split())
        for s in _CANDIDATE_SYMS:
            if s in names and s not in found:
                found.append(s)
        if found:
            break
    return found


def _parse_bpftrace_counts(text: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for m in re.finditer(r'@\w+\["([^"]+)"\]:\s*([\d]+)', text):
        counts[m.group(1)] = counts.get(m.group(1), 0.0) + float(m.group(2))
    for m in re.finditer(r'@\w+\[([A-Za-z0-9_]+)\]:\s*([\d]+)', text):
        counts[m.group(1)] = counts.get(m.group(1), 0.0) + float(m.group(2))
    return counts


class EbpfProfilerProvider(BaseProfilerProvider):
    name = "ebpf"

    def __init__(self) -> None:
        super().__init__()
        self._bpftrace = which_binary("bpftrace")
        self._bcc = which_binary("bcc-tools") or which_binary("funccount")
        self._enabled = _env_flag("NSA_EBPF_PROFILE")
        self._symbols: list[str] | None = None

    def capabilities(self) -> ProviderCapabilities:
        self._enabled = _env_flag("NSA_EBPF_PROFILE")
        linux = is_linux()
        tools = bool(self._bpftrace or self._bcc)
        pid = _target_pid()
        binary = _binary_path(pid)
        reasons: list[str] = []
        if not linux:
            reasons.append("not_linux")
        if not tools:
            reasons.append("bpf_tools_missing")
        if not self._enabled:
            reasons.append("NSA_EBPF_PROFILE_not_set")
        if self._enabled and tools and linux and not pid:
            reasons.append("NSA_PERF_PID_missing")
        state = (
            CapabilityState.AVAILABLE
            if (linux and tools and self._enabled and pid)
            else CapabilityState.UNAVAILABLE
        )
        return ProviderCapabilities(
            name=self.name,
            state=state,
            features={
                "bpftrace": bool(self._bpftrace),
                "bcc": bool(self._bcc),
                "profile_enabled": self._enabled,
                "target_pid": pid or 0,
                "binary": binary or "",
                "uprobes": bool(binary),
            },
            reasons=reasons,
        )

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        self._enabled = _env_flag("NSA_EBPF_PROFILE")
        self._initialized = True

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        caps = self.capabilities()
        if caps.state != CapabilityState.AVAILABLE or not self._bpftrace:
            return empty_batch(self.name, session)

        pid = _target_pid()
        binary = _binary_path(pid)
        if pid is None or not binary:
            return empty_batch(self.name, session)

        if self._symbols is None:
            self._symbols = _discover_symbols(binary)

        duration_s = max(1, min(5, int((getattr(session, "sample_interval_ms", 1000) or 1000) / 1000) or 1))

        try:
            with tempfile.NamedTemporaryFile("w", suffix=".bt", delete=False, encoding="utf-8") as fh:
                script_path = fh.name
                if self._symbols:
                    for s in self._symbols:
                        fh.write(f'uprobe:{binary}:{s} {{ @hits["{s}"] = count(); }}\n')
                    fh.write(f"interval:s:{duration_s} {{ exit(); }}\n")
                else:
                    fh.write(f"profile:hz:99 /pid == {pid}/ {{ @samples = count(); }}\n")
                    fh.write(f"interval:s:{duration_s} {{ exit(); }}\n")

            proc = subprocess.run(
                [self._bpftrace, script_path],
                capture_output=True,
                text=True,
                timeout=duration_s + 8,
                check=False,
            )
            try:
                Path(script_path).unlink(missing_ok=True)
            except Exception:
                pass

            blob = f"{proc.stdout}\n{proc.stderr}"
            if proc.returncode != 0:
                self._failures += 1
                self._last_error = blob[:500]
                logger.debug("bpftrace failed rc=%s: %s", proc.returncode, self._last_error)
                return empty_batch(self.name, session)

            counts = _parse_bpftrace_counts(blob)
            sample_m = re.search(r"@samples:\s*([\d]+)", blob)
            values: dict[str, float] = {
                "ebpf.available": 1.0,
                "ebpf.symbols_found": float(len(self._symbols or [])),
                "ebpf.target_pid": float(pid),
                "ebpf.oncpu_samples": float(sample_m.group(1)) if sample_m else 0.0,
            }
            for name, val in counts.items():
                safe = re.sub(r"[^a-zA-Z0-9_]+", "_", name)
                values[f"ebpf.op.{safe}"] = float(val)
                values["ebpf.operator_hits"] = values.get("ebpf.operator_hits", 0.0) + float(val)
            self._failures = 0
            return samples_from_mapping(self.name, session, values)
        except Exception as exc:
            self._failures += 1
            self._last_error = str(exc)
            logger.debug("ebpf sample failed: %s", exc)
            return empty_batch(self.name, session)

    def shutdown(self) -> None:
        self._initialized = False
        self._symbols = None
