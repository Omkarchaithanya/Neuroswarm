"""QuantCatalog — YAML-driven quantization profiles."""

from __future__ import annotations

from typing import Any, Mapping

from ..models import QuantProfile


class QuantCatalog:
    def __init__(self, quants_cfg: Mapping[str, Any] | None = None) -> None:
        self._profiles: dict[str, QuantProfile] = {}
        raw = dict((quants_cfg or {}).get("profiles") or {})
        for name, data in raw.items():
            if not isinstance(data, Mapping):
                continue
            self._profiles[str(name)] = QuantProfile(
                name=str(name),
                bits=float(data.get("bits", 4.0)),
                quality=float(data.get("quality", 0.5)),
                latency=float(data.get("latency", 0.5)),
                memory=float(data.get("memory", 0.5)),
                expected_perplexity=float(data.get("expected_perplexity", 5.0)),
                arm_kernel=bool(data.get("arm_kernel", False)),
                kleidiai=bool(data.get("kleidiai", False)),
                llama_cpp=bool(data.get("llama_cpp", True)),
                vllm=bool(data.get("vllm", False)),
                executorch=bool(data.get("executorch", False)),
                litert=bool(data.get("litert", False)),
                supported=bool(data.get("supported", True)),
                workloads=[str(w) for w in (data.get("workloads") or [])],
            )

    def get(self, name: str) -> QuantProfile | None:
        return self._profiles.get(name)

    def list(self, *, supported_only: bool = True) -> list[QuantProfile]:
        items = list(self._profiles.values())
        if supported_only:
            items = [p for p in items if p.supported]
        return sorted(items, key=lambda p: p.bits)

    def names(self, *, supported_only: bool = True) -> list[str]:
        return [p.name for p in self.list(supported_only=supported_only)]

    def supports_backend(self, quant: str, backend: str) -> bool:
        profile = self.get(quant)
        if profile is None or not profile.supported:
            return False
        key = backend.lower().replace("-", "_")
        mapping = {
            "llama_cpp": profile.llama_cpp,
            "vllm": profile.vllm,
            "executorch": profile.executorch,
            "litert": profile.litert,
            "sglang": profile.vllm,
            "mock": True,
        }
        return bool(mapping.get(key, profile.llama_cpp))
