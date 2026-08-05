"""BackendFactory — construct backends from DIPA config / env (plugin spine)."""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.backends.llama_cpp import LlamaCppBackend
from neuroswarm_arm.runtime.dipa.backends.mock_backend import MockBackend
from neuroswarm_arm.runtime.dipa.backends.registry import BackendRegistry
from neuroswarm_arm.runtime.dipa.backends.sglang import SGLangBackend
from neuroswarm_arm.runtime.dipa.runtime.runtime_config import DIPARuntimeConfig
from neuroswarm_arm.runtime.haoe.topology.numa_status import (
    build_numa_bind_argv,
    collect_numa_status,
    llama_numa_flag,
)

logger = logging.getLogger(__name__)


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
        numa_status = collect_numa_status()
        node_ids = sorted(int(k) for k in numa_status.cpulists.keys()) or [0]
        logger.info(
            "numa_policy=%s locality_mode=%s nodes=%s cross_numa=%s cpusets=%s",
            numa_status.policy,
            numa_status.locality_mode,
            numa_status.numa_nodes,
            numa_status.cross_numa_penalty_applicable,
            numa_status.cpuset_strings,
        )

        if use_mock or not urls:
            for name in ("tier1", "tier2", "tier3", "mock", "llama_cpp"):
                if registry.get(name) is None:
                    registry.register(MockBackend(name=name))
        else:
            slot_dir = Path(os.getenv("NSA_LLAMA_SLOT_DIR", "/tmp/neuroswarm-slots"))
            LlamaCppBackend.slot_dir = slot_dir
            for tier_name, url in urls.items():
                if registry.get(tier_name) is None:
                    tier_n = _tier_num(tier_name)
                    numa_bind = build_numa_bind_argv(tier=tier_n, nodes=node_ids)
                    registry.register(
                        LlamaCppBackend(
                            name=tier_name,
                            base_url=url,
                            tier=tier_n,
                            numa_bind=numa_bind,
                        )
                    )
            if registry.get("llama_cpp") is None and urls:
                # Alias decode backend to preferred tier.
                prefer = urls.get("tier2") or next(iter(urls.values()))
                numa_bind = build_numa_bind_argv(tier=2, nodes=node_ids)
                registry.register(
                    LlamaCppBackend(
                        name="llama_cpp",
                        base_url=prefer,
                        tier=2,
                        numa_bind=numa_bind,
                    )
                )
            # Surface planned llama --numa for managed launches (ProcessSupervisor).
            _ = llama_numa_flag(node_ids)
            for name in ("tier1", "tier2", "tier3"):
                if registry.get(name) is None:
                    registry.register(MockBackend(name=name))

        self.register_sglang(registry, use_mock=use_mock)
        self.register_mlx(registry, use_mock=use_mock)
        self._inject_draft_models(registry)
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

    def register_mlx(self, registry: BackendRegistry, *, use_mock: bool = False) -> None:
        """Register the MLX backend on macOS when mlx-lm is available.

        Gated by ``sys.platform == "darwin"`` and
        ``importlib.util.find_spec("mlx")``.  No-op on Linux / when
        ``mlx-lm`` is not installed (``uv sync --extra apple``).
        """
        if registry.get("mlx") is not None:
            return
        if use_mock or sys.platform != "darwin":
            return
        if importlib.util.find_spec("mlx") is None:
            return
        try:
            from neuroswarm_arm.runtime.dipa.backends.mlx import MlxBackend
        except ImportError:
            return
        port = int(os.getenv("NSA_MLX_PORT", "8080"))
        registry.register(
            MlxBackend(
                name="mlx",
                base_url=f"http://127.0.0.1:{port}",
            )
        )

    def _inject_draft_models(self, registry: BackendRegistry) -> None:
        if not _speculation_enabled(self.config):
            return
        tier_spec_url = os.getenv("NSA_TIER_SPEC_URL", "").strip()
        if tier_spec_url:
            for backend in registry.all():
                if isinstance(backend, LlamaCppBackend):
                    backend.configure_draft(draft_base_url=tier_spec_url)
            return

        draft = _resolve_draft_config(self.config)
        if not draft["path"]:
            return
        draft_path = Path(str(draft["path"])).expanduser()
        if not draft_path.exists():
            logger.warning(
                "Draft model file does not exist: %s; disabling speculative draft pairing",
                draft_path,
            )
            for backend in registry.all():
                if isinstance(backend, LlamaCppBackend):
                    backend.capabilities.speculation = False
                    backend.capabilities.self_speculation = False
            return

        draft_port = str(draft["port"])
        draft_base_url = f"http://127.0.0.1:{draft_port}"
        draft_command = [
            "llama-server",
            "-m",
            str(draft_path),
            "--port",
            draft_port,
            "-c",
            str(draft["ctx_size"]),
            "-t",
            str(draft["n_threads"]),
            "--host",
            "127.0.0.1",
        ]

        for backend in registry.all():
            if not isinstance(backend, LlamaCppBackend):
                continue
            backend.configure_draft(
                draft_base_url=draft_base_url,
                draft_command=draft_command,
            )
            supervisor = getattr(backend, "_supervisor", None)
            if supervisor is None:
                continue
            try:
                supervisor.start_draft(
                    backend.name,
                    draft_command,
                    base_url=draft_base_url,
                )
            except KeyError:
                # Target process metadata is created by LlamaCppBackend.start(); the
                # backend will launch the prepared draft command immediately after.
                continue


def _tier_num(name: str) -> int:
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 0


def _speculation_enabled(config: DIPARuntimeConfig) -> bool:
    cascade_spec = dict(config.cascade.get("speculation") or {})
    ascr = dict(config.cascade.get("ascr") or {})
    return bool(
        cascade_spec.get("enabled")
        or cascade_spec.get("speculation")
        or ascr.get("enabled")
    )


def _resolve_draft_config(config: DIPARuntimeConfig) -> dict[str, Any]:
    raw = config.draft_models if isinstance(config.draft_models, Mapping) else {}
    return {
        "path": (
            os.getenv("NSA_DRAFT_MODEL_PATH", "").strip()
            or str(
                raw.get("path")
                or raw.get("model_path")
                or raw.get("draft_path")
                or ""
            )
        ),
        "port": int(os.getenv("NSA_DRAFT_PORT", "") or raw.get("port") or 8081),
        "ctx_size": int(
            os.getenv("NSA_DRAFT_CTX_SIZE", "") or raw.get("ctx_size") or 2048
        ),
        "n_threads": int(
            os.getenv("NSA_DRAFT_N_THREADS", "") or raw.get("n_threads") or 4
        ),
    }
