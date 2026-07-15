"""BackendFactory — construct backends from DIPA config / env (plugin spine)."""

from __future__ import annotations

import os
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.backends.llama_cpp import LlamaCppBackend
from neuroswarm_arm.runtime.dipa.backends.mock_backend import MockBackend
from neuroswarm_arm.runtime.dipa.backends.registry import BackendRegistry
from neuroswarm_arm.runtime.dipa.backends.sglang import SGLangBackend
from neuroswarm_arm.runtime.dipa.runtime.runtime_config import DIPARuntimeConfig


class BackendFactory:
    """Create and register inference backends without leaking engine types upward."""

    def __init__(self, config: DIPARuntimeConfig | None = None) -> None:
        self.config = config or DIPARuntimeConfig()

    def build_registry(
        self,
        *,
        tier_urls: Mapping[str, str] | None = None,
        use_mock: bool = False,
        existing: BackendRegistry | None = None,
    ) -> BackendRegistry:
        registry = existing or BackendRegistry()
        urls = dict(tier_urls or {})

        if use_mock or not urls:
            for name in ("tier1", "tier2", "tier3", "mock", "llama_cpp"):
                if registry.get(name) is None:
                    registry.register(MockBackend(name=name))
        else:
            for tier_name, url in urls.items():
                if registry.get(tier_name) is None:
                    registry.register(
                        LlamaCppBackend(
                            name=tier_name,
                            base_url=url,
                            tier=_tier_num(tier_name),
                        )
                    )
            if registry.get("llama_cpp") is None and urls:
                # Alias decode backend to preferred tier.
                prefer = urls.get("tier2") or next(iter(urls.values()))
                registry.register(
                    LlamaCppBackend(name="llama_cpp", base_url=prefer, tier=2)
                )
            for name in ("tier1", "tier2", "tier3"):
                if registry.get(name) is None:
                    registry.register(MockBackend(name=name))

        self.register_sglang(registry, use_mock=use_mock)
        return registry

    def register_sglang(self, registry: BackendRegistry, *, use_mock: bool = False) -> None:
        if registry.get("sglang") is not None:
            return
        if use_mock:
            registry.register(MockBackend(name="sglang", tier=0))
            return
        url = self.config.sglang_url or os.getenv("NSA_DIPA_SGLANG_URL", "").strip()
        router = self.config.sglang_router_url or os.getenv(
            "NSA_DIPA_SGLANG_ROUTER_URL", ""
        ).strip()
        native = self.config.pd_mode == "native"
        registry.register(
            SGLangBackend(
                name="sglang",
                base_url=url or "http://127.0.0.1:30000",
                router_url=router,
                native_pd=native,
            )
        )


def _tier_num(name: str) -> int:
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 0
