"""MAKSConnector — capability-aware DIPA port to Memory OS."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..interfaces.kv_cache import IKVCacheConnector


class SupportsKVSharing(Protocol):
    async def store(self, key: str, data: bytes) -> None: ...

    async def load(self, key: str) -> bytes: ...

    async def share(self, key: str, consumer_id: str) -> str: ...

    async def release(self, key: str, consumer_id: str) -> None: ...


class MAKSConnector(IKVCacheConnector):
    """Adapt Layer-5 MAKS / sharing backends — DIPA never owns storage."""

    def __init__(
        self,
        sharing: SupportsKVSharing | None = None,
        *,
        backend_id: str = "opaque",
    ) -> None:
        self._sharing = sharing
        self._local: dict[str, bytes] = {}
        self._manager = None
        self._backend_id = backend_id
        if sharing is not None and hasattr(sharing, "create") and hasattr(sharing, "lookup"):
            self._manager = sharing
            # Prefer manager default backend if present
            if hasattr(sharing, "default_backend_id"):
                self._backend_id = str(getattr(sharing, "default_backend_id") or backend_id)

    def _caps(self):
        if self._manager is not None and hasattr(self._manager, "capabilities"):
            return self._manager.capabilities.flags(self._backend_id)
        return None

    def supports_prefix_reuse(self) -> bool:
        caps = self._caps()
        return True if caps is None else caps.prefix_reuse

    def supports_shared_kv(self) -> bool:
        caps = self._caps()
        return True if caps is None else caps.shared_kv

    def supports_paged_kv(self) -> bool:
        caps = self._caps()
        return False if caps is None else caps.paged_kv

    def supports_speculative_kv(self) -> bool:
        caps = self._caps()
        return False if caps is None else caps.speculative_kv

    def supports_cross_session_reuse(self) -> bool:
        caps = self._caps()
        return True if caps is None else caps.cross_session_reuse

    def supports_cross_model_reuse(self) -> bool:
        caps = self._caps()
        return False if caps is None else caps.cross_model_reuse

    def capability_matrix(self) -> dict[str, dict[str, bool]]:
        if self._manager is not None and hasattr(self._manager, "capability_matrix"):
            return self._manager.capability_matrix()
        return {}

    async def load(self, session_id: str, agent_id: str = "") -> str | None:
        key = session_id or agent_id
        if not key:
            return None
        if self._manager is not None and hasattr(self._manager, "_find_by_session"):
            try:
                rec = await self._manager._find_by_session(key)  # type: ignore[union-attr]
                if rec is not None:
                    return rec.kv_id
            except Exception:
                pass
        if self._sharing is not None:
            try:
                data = await self._sharing.load(key)
                if data:
                    return key
            except Exception:
                return None
        if key in self._local:
            return key
        return None

    async def save(
        self,
        session_id: str,
        payload: bytes,
        *,
        agent_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        key = session_id or agent_id or "anon"
        meta = dict(metadata or {})
        backend_id = str(meta.get("backend_id", meta.get("backend", self._backend_id)) or self._backend_id)
        if self._manager is not None:
            try:
                from neuroswarm_arm.runtime.maks.models import KVIdentity

                identity = KVIdentity(
                    model_id=str(meta.get("model_id", meta.get("model", ""))),
                    quantization=str(meta.get("quantization", meta.get("quant", ""))),
                    tokenizer_version=str(meta.get("tokenizer_version", "")),
                    rope_config=str(meta.get("rope_config", "")),
                    context_window=int(meta.get("context_window", 0) or 0),
                )
                # Cross-model reuse never assumed — identity fingerprints gate dedup
                handle = await self._manager.create(  # type: ignore[union-attr]
                    payload,
                    agent_id=agent_id,
                    session_id=session_id or key,
                    identity=identity,
                    prompt_hash=str(meta.get("prompt_hash", "")),
                    priority=int(meta.get("priority", 0) or 0),
                    backend_id=backend_id,
                    cascade_stage=int(meta.get("cascade_stage", 0) or 0),
                    reasoning_depth=int(meta.get("reasoning_depth", 0) or 0),
                    importance=float(meta.get("importance", 0.0) or 0.0),
                )
                return handle.kv_id
            except Exception:
                if self._sharing is not None:
                    await self._sharing.store(key, payload)
                return key
        if self._sharing is not None:
            await self._sharing.store(key, payload)
        else:
            self._local[key] = payload
        return key

    async def share(self, key: str, consumer_id: str) -> str:
        if not self.supports_shared_kv():
            return f"share-denied:{key}:{consumer_id}"
        if self._sharing is not None:
            return await self._sharing.share(key, consumer_id)
        return f"share:{key}:{consumer_id}"

    async def release(self, key: str, consumer_id: str = "") -> None:
        if self._sharing is not None:
            await self._sharing.release(key, consumer_id)
        else:
            self._local.pop(key, None)
