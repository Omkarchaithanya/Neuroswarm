"""Official Mem0 SDK client — ONLY module that imports ``mem0ai``.

Maps NEXUS config → ``Memory.from_config`` (OSS v3, no graph_store / Neo4j).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.memory.embeddings import hash_embed
from neuroswarm_arm.runtime.memory.exceptions import MemoryProviderError
from neuroswarm_arm.runtime.memory.logging import log_event


def _clear_qdrant_locks(path: Path) -> None:
    """Drop stale local Qdrant locks left by prior container processes."""
    root = Path(path)
    if not root.exists():
        return
    for pattern in (".lock", "*.lock", "lock", ".qdrant-lock"):
        for hit in root.glob(pattern):
            try:
                if hit.is_file():
                    hit.unlink(missing_ok=True)
            except Exception:
                pass
    # Nested lock files from embedded qdrant
    for hit in root.rglob("*.lock"):
        try:
            hit.unlink(missing_ok=True)
        except Exception:
            pass


def _hash_embedder(dims: int = 1536):
    """Local deterministic embedder for NSA_MEM_LLM=none (no cloud / llama --embeddings).

    Dims default to 1536 to match Mem0's OpenAI embedder collection shape.
    """
    try:
        from mem0.embeddings.base import EmbeddingBase
    except Exception:  # noqa: BLE001
        EmbeddingBase = object  # type: ignore[misc, assignment]

    class HashEmbedding(EmbeddingBase):  # type: ignore[valid-type]
        def __init__(self, config: Any = None) -> None:
            self.config = config
            self.dims = dims
            # Mem0/Qdrant may read embedding_dims from config.
            if hasattr(config, "embedding_dims"):
                try:
                    self.dims = int(getattr(config, "embedding_dims") or dims)
                except Exception:
                    pass

        def embed(self, text, memory_action=None):  # noqa: ANN001
            return hash_embed(str(text or ""), dims=self.dims)

    return HashEmbedding()


def build_mem0_config(cfg: MemoryRuntimeConfig) -> dict[str, Any]:
    """Map runtime config → Mem0 OSS Memory() config (v3, no graph_store)."""
    import os

    qdrant_url = (os.getenv("NSA_MEM_QDRANT_URL") or "").strip()
    if qdrant_url:
        # Server mode — preferred for Compose (no embedded single-writer locks).
        from urllib.parse import urlparse

        parsed = urlparse(qdrant_url if "://" in qdrant_url else f"http://{qdrant_url}")
        host = parsed.hostname or "qdrant"
        port = int(parsed.port or 6333)
        vector_store: dict[str, Any] = {
            "provider": "qdrant",
            "config": {
                "collection_name": cfg.collection_name,
                "host": host,
                "port": port,
            },
        }
    else:
        vector_store = {
            "provider": "qdrant",
            "config": {
                "collection_name": cfg.collection_name,
                "path": str(cfg.qdrant_path),
                "on_disk": True,
            },
        }

    config: dict[str, Any] = {
        "vector_store": vector_store,
        "version": "v1.1",
        # Keep Mem0 history/migrations off the default /root/.mem0 path when possible.
        "history_db_path": str(cfg.store_root / "mem0_history.db"),
    }
    if cfg.llm_mode == "none":
        # Placeholder credentials satisfy Mem0 init; we swap in HashEmbedding after.
        config["llm"] = {
            "provider": "openai",
            "config": {
                "model": "gpt-4o-mini",
                "api_key": "local-none",
                "openai_base_url": "http://127.0.0.1:9/v1",
            },
        }
        config["embedder"] = {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": "local-none",
                "openai_base_url": "http://127.0.0.1:9/v1",
            },
        }
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
        # local (and any other OpenAI-compatible base)
        base_raw = (cfg.llm_base_url or "http://127.0.0.1:8080").rstrip("/")
        if base_raw.endswith("/v1"):
            base = base_raw
        else:
            base = f"{base_raw}/v1"
        config["llm"] = {
            "provider": "openai",
            "config": {
                "model": cfg.llm_model,
                "api_key": cfg.llm_api_key or "local",
                "openai_base_url": base,
            },
        }
        # custom_instructions is appended by Mem0; the huge v3 ADDITIVE system
        # prompt is replaced after init via _install_lean_extraction_prompt.
        config["custom_instructions"] = (
            "Extract at most 5 short factual memories. Prefer user preferences."
        )
        # Default embedder for local demos: hash (llama often has no /embeddings).
        # Set NSA_MEM_EMBEDDER=openai to use the same OpenAI-compatible base.
        embedder_mode = (os.getenv("NSA_MEM_EMBEDDER") or "hash").strip().lower()
        if embedder_mode in {"openai", "remote", "llama"}:
            config["embedder"] = {
                "provider": "openai",
                "config": {
                    "model": cfg.embedder_model,
                    "api_key": cfg.llm_api_key or "local",
                    "openai_base_url": base,
                },
            }
        else:
            config["embedder"] = {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": "local-hash",
                    "openai_base_url": "http://127.0.0.1:9/v1",
                },
            }
    return config


# Lean replacement for Mem0 v3 ADDITIVE_EXTRACTION_PROMPT (~8k tokens).
_LEAN_EXTRACTION_SYSTEM = """You extract durable user/agent facts for a memory store.
Return ONLY valid JSON of the form:
{"memory":[{"text":"<short fact>"}]}
Rules:
- At most 5 facts; each fact one short sentence.
- Prefer preferences, identity, and durable constraints.
- No preamble, markdown, or commentary.
"""


def _install_lean_extraction_prompt(memory: Any) -> None:
    """Replace Mem0's huge additive system prompt so local 4k/8k tiers can extract."""
    try:
        import mem0.memory.utils as mem_utils  # type: ignore
    except Exception:
        mem_utils = None
    if mem_utils is not None and hasattr(mem_utils, "ADDITIVE_EXTRACTION_PROMPT"):
        try:
            mem_utils.ADDITIVE_EXTRACTION_PROMPT = _LEAN_EXTRACTION_SYSTEM
        except Exception:
            pass
    # Also patch common attribute locations on the Memory instance.
    for attr in ("additive_prompt", "ADDITIVE_EXTRACTION_PROMPT", "_additive_prompt"):
        if hasattr(memory, attr):
            try:
                setattr(memory, attr, _LEAN_EXTRACTION_SYSTEM)
            except Exception:
                pass
    # mem0 may import the constant into memory.main — best-effort patch.
    try:
        import mem0.memory.main as mem_main  # type: ignore

        if hasattr(mem_main, "ADDITIVE_EXTRACTION_PROMPT"):
            mem_main.ADDITIVE_EXTRACTION_PROMPT = _LEAN_EXTRACTION_SYSTEM
    except Exception:
        pass


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
                import os

                os.environ.setdefault("MEM0_DIR", str(cfg.store_root / "mem0_home"))
                _clear_qdrant_locks(cfg.qdrant_path)
                (cfg.store_root / "mem0_home").mkdir(parents=True, exist_ok=True)
                cfg.qdrant_path.mkdir(parents=True, exist_ok=True)
                self._memory = Memory.from_config(build_mem0_config(cfg))
                if cfg.llm_mode == "local":
                    _install_lean_extraction_prompt(self._memory)
                # Hash embedder when LLM disabled, or local demo without /embeddings.
                use_hash = cfg.llm_mode == "none"
                if not use_hash and cfg.llm_mode == "local":
                    use_hash = (os.getenv("NSA_MEM_EMBEDDER") or "hash").strip().lower() not in {
                        "openai",
                        "remote",
                        "llama",
                    }
                if use_hash:
                    emb = _hash_embedder(1536)
                    for attr in ("embedding_model", "embedder", "_embedder"):
                        if hasattr(self._memory, attr):
                            setattr(self._memory, attr, emb)
                log_event("mem0_init", status="ok", path=str(cfg.qdrant_path), llm_mode=cfg.llm_mode)
            except Exception as exc:  # noqa: BLE001
                self._init_error = str(exc)
                self._memory = None
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
        infer: bool | None = None,
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
        # Local tier demos: try LLM extraction, then store raw on overflow/failure.
        want_infer = True if infer is None else bool(infer)
        if infer is not None:
            kwargs["infer"] = want_infer
        try:
            result = m.add(messages, **kwargs)
        except Exception as exc:  # noqa: BLE001
            if want_infer and self.cfg.llm_mode == "local":
                log_event("mem0_add_fallback", reason=str(exc)[:200], infer=False)
                kwargs["infer"] = False
                return m.add(messages, **kwargs)
            raise
        # Empty results after failed extraction — store verbatim for recall demos.
        items: list[Any] = []
        if isinstance(result, dict):
            items = list(result.get("results") or result.get("memories") or [])
        elif isinstance(result, list):
            items = result
        if want_infer and self.cfg.llm_mode == "local" and not items:
            log_event("mem0_add_fallback", reason="empty_extraction", infer=False)
            kwargs["infer"] = False
            return m.add(messages, **kwargs)
        return result

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
        try:
            raw = m.search(query, filters=filters, top_k=top_k, threshold=threshold, rerank=rerank)
        except Exception:  # noqa: BLE001
            # Dimension mismatch / Qdrant hiccups must not break chat.
            return []
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
