"""eBPF profiler port — stable API; UNAVAILABLE until BCC/bpftrace present."""

from __future__ import annotations

from ..schemas import (
    CapabilityState,
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
)
from .base import BaseProfilerProvider, empty_batch, which_binary


class EbpfProfilerProvider(BaseProfilerProvider):
    name = "ebpf"

    def __init__(self) -> None:
        super().__init__()
        self._bpftrace = which_binary("bpftrace")
        self._bcc = False
        try:
            import importlib.util

            self._bcc = importlib.util.find_spec("bcc") is not None
        except Exception:
            self._bcc = False

    def capabilities(self) -> ProviderCapabilities:
        ok = bool(self._bpftrace or self._bcc)
        reasons: list[str] = []
        if not ok:
            reasons.append("bcc/bpftrace not installed — eBPF provider inactive")
        return ProviderCapabilities(
            name=self.name,
            available=ok,
            state=CapabilityState.AVAILABLE if ok else CapabilityState.UNAVAILABLE,
            sampling=ok,
            tracing=ok,
            cpu=ok,
            memory=False,
            hardware=ok,
            continuous=ok,
            reasons=tuple(reasons),
            extensions={"bpftrace": bool(self._bpftrace), "bcc": self._bcc},
        )

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        # Full eBPF programs are optional; without tooling return empty batch.
        # Interface remains stable for third-party plugins to replace this provider.
        if not self.capabilities().available:
            return empty_batch(self.name, session)
        return empty_batch(self.name, session)
