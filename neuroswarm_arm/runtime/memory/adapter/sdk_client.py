"""Official Mem0 SDK client — ONLY module that imports ``mem0ai``.

Maps NEXUS config → ``Memory.from_config`` (OSS v3, no graph_store / Neo4j).
"""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.exceptions import MemoryProviderError
from neuroswarm_arm.runtime.memory.logging import log_event


def build_mem0_config(cfg: MemoryRuntimeConfig) -> dict[str, Any]:
    """Map runtime config → Mem0 OSS Memory() config (v3, no graph_store)."""
    config: dict[str, Any] = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": cfg.collection_name,
                "path": str(cfg.qdrant_path),
                "on_disk": True,
            },
        },
        "version": "v1.1",
    }
    if cfg.llm_mode == "none":
        return config
    if cfg.llm_mode == "openai":
        config["llm"] = {
            "provider": "openai",
            "config": {"model": cfg.llm_model, "api_key": cfg.llm_api_key},
        }
        config["embedder"] = {
            "provider": "openai",
            "config": {"model": cfg.embedder_model, "api_key": cfg.llm_api_key},
        }
    else:
        base = cfg.llm_base_url.rstrip("/") + "/v1"
        config["llm"] = {
            "provider": "openai",
            "config": {
                "model": cfg.llm_model,
                "api_key": cfg.llm_api_key or "local",
                "openai_base_url": base,
            },
        }
        config["embedder"] = {
            "provider": "openai",
            "config": {
                "model": cfg.embedder_model,
                "api_key": cfg.llm_api_key or "local",
                "openai_base_url": base,
            },
        }
    return config


class Mem0SdkClient:
    """Thin wrap over ``mem0.Memory`` — v3 filters + ADD-only add."""

    def __init__(self, cfg: MemoryRuntimeConfig, memory: Any | None = None, *, disabled: bool = False) -> None:
        self.cfg = cfg
        self._memory: Any | None = memory
        self._init_error: str | None = None
        if disabled:
            self._init_error = "disabled"
            return
        if self._memory is None:
            try:
                from mem0 import Memory  # sole mem0ai import site

                self._memory = Memory.from_config(build_mem0_config(cfg))
                log_event("mem0_init", status="ok", path=str(cfg.qdrant_path))
            except Exception as exc:  # noqa: BLE001
                self._init_error = str(exc)
                log_event("mem0_init", status="failed", error=str(exc))

    @property
    def available(self) -> bool:
        return self._memory is not None

    def require(self) -> Any:
        if self._memory is None:
            raise MemoryProviderError(f"mem0 unavailable: {self._init_error}")
        return self._memory

    def add(
        self,
        messages: str | list[dict[str, str]],
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        m = self.require()
        kwargs: dict[str, Any] = {}
        if user_id:
            kwargs["user_id"] = user_id
        if agent_id:
            kwargs["agent_id"] = agent_id
        if run_id:
            kwargs["run_id"] = run_id
        if metadata:
            kwargs["metadata"] = metadata
        return m.add(messages, **kwargs)

    def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        top_k: int = 5,
        threshold: float = 0.1,
        rerank: bool = False,
    ) -> list[dict[str, Any]]:
        m = self.require()
        filters: dict[str, Any] = {}
        if user_id:
            filters["user_id"] = user_id
        if agent_id:
            filters["agent_id"] = agent_id
        if run_id:
            filters["run_id"] = run_id
        if not filters:
            filters["user_id"] = "default"
        raw = m.search(query, filters=filters, top_k=top_k, threshold=threshold, rerank=rerank)
        if isinstance(raw, dict):
            return list(raw.get("results") or [])
        return list(raw or [])

    def get(self, memory_id: str) -> dict[str, Any] | None:
        try:
            return self.require().get(memory_id)
        except Exception:  # noqa: BLE001
            return None

    def delete(self, memory_id: str) -> bool:
        try:
            self.require().delete(memory_id)
            return True
        except Exception:  # noqa: BLE001
            return False

    def get_all(self, *, user_id: str, top_k: int = 100) -> list[dict[str, Any]]:
        m = self.require()
        try:
            raw = m.get_all(filters={"user_id": user_id})
            if isinstance(raw, dict):
                return list(raw.get("results") or [])[:top_k]
            return list(raw or [])[:top_k]
        except Exception:  # noqa: BLE001
            return self.search("*", user_id=user_id, top_k=top_k, threshold=0.0)

    def health(self) -> dict[str, Any]:
        return {
            "provider": "mem0",
            "available": self.available,
            "error": self._init_error,
            "qdrant_path": str(self.cfg.qdrant_path),
            "healthy": self.available,
        }


# Back-compat alias
Mem0Client = Mem0SdkClient
