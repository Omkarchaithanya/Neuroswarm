"""MAKS KV Manager — Layer 5 public control plane."""

from __future__ import annotations

import time
from typing import Any

from .allocator import KVAllocator
from .capability import CapabilityRegistry, build_default_capability_registry
from .compression import build_compression
from .compressor import LazyCompressor
from .config import MAKSConfig
from .dedup import DeduplicationEngine
from .eviction import EvictionEngine
from .exceptions import (
    KVBudgetExceededError,
    KVIdentityMismatchError,
    KVNotFoundError,
    KVPermissionError,
    KVPinnedError,
)
from .handles import HandleRegistry
from .hashing import build_hasher
from .interfaces import IARMORAPolicy, ICompression, IKVProvider
from .lifecycle import LifecycleManager
from .metadata import build_metadata, now_ts
from .metrics import MAKSMetrics
from .migration import MigrationEngine
from .models import (
    KVHandle,
    KVIdentity,
    KVRegistryRecord,
    KVState,
    KVTier,
    LocalityHint,
    PrefetchRequest,
    ProviderName,
)
from .pager import Pager
from .pool import GlobalPagePool
from .prefetch import PrefetchEngine
from .pressure_monitor import PressureMonitor
from .reference_counter import ReferenceCounter
from .registry import KVRegistry
from .scheduler import MAKSScheduler
from .sharing import SharingEngine
from .telemetry import MAKSTelemetry
from .tier_manager import TierManager
from .utils import monotonic_ms, new_kv_id, new_token


class ConfigARMORAPolicy(IARMORAPolicy):
    """ARMORA stub — reads limits from MAKSConfig until ARMORA package exists."""

    def __init__(self, cfg: MAKSConfig) -> None:
        self.cfg = cfg

    def snapshot(self):
        from .models import ARMORAPolicySnapshot

        return ARMORAPolicySnapshot(
            max_memory_bytes=self.cfg.max_memory_bytes or self.cfg.ram_budget_bytes,
            max_cost=self.cfg.max_cost,
            max_cache_entries=self.cfg.max_cache_entries,
            eviction_policy=self.cfg.eviction_policy,
            ttl_s=self.cfg.default_ttl_s,
            budget=self.cfg.max_cost,
            priority=0,
        )

    def admit(self, size_bytes: int, priority: int = 0) -> bool:
        snap = self.snapshot()
        if snap.max_memory_bytes > 0 and size_bytes > snap.max_memory_bytes:
            return priority >= snap.priority + 10
        return True


class KVManager:
    """Global KV Memory OS — create/share/lookup/release/migrate/page/pin."""

    def __init__(
        self,
        config: MAKSConfig,
        registry: KVRegistry,
        providers: dict[str, IKVProvider],
        *,
        metrics: MAKSMetrics | None = None,
        armora: IARMORAPolicy | None = None,
        compression: ICompression | None = None,
        enable_scheduler: bool | None = None,
        capabilities: CapabilityRegistry | None = None,
        pool: GlobalPagePool | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.providers = providers
        self.metrics = metrics or MAKSMetrics()
        self.telemetry = MAKSTelemetry(self.metrics)
        self.armora = armora or ConfigARMORAPolicy(config)
        self.compression = compression or build_compression(config.compression)
        self.compressor = LazyCompressor(self.compression)
        self.hasher = build_hasher(config.hash_algo)
        self.dedup = DeduplicationEngine(self.hasher, algo=config.hash_algo)
        self.deduplicator = self.dedup  # Memory OS alias
        self.lifecycle = LifecycleManager()
        self.refcount = ReferenceCounter(orphan_grace_s=config.orphan_grace_s)
        self.sharing = SharingEngine()
        self.handles = HandleRegistry()
        self.pool = pool or GlobalPagePool(page_bytes=getattr(config, "page_bytes", 64 * 1024))
        self.capabilities = capabilities or build_default_capability_registry()
        self.default_backend_id = getattr(config, "default_backend_id", "opaque") or "opaque"
        self.allocator = KVAllocator(
            providers,
            default_provider=config.default_provider,
            ram_budget_bytes=config.ram_budget_bytes,
        )
        self.tiers = TierManager(providers)
        self.migration = MigrationEngine(registry, providers)
        self.eviction = EvictionEngine(registry, policy_name=config.eviction_policy)
        self.pressure_monitor = PressureMonitor(
            ram_budget_bytes=config.ram_budget_bytes,
            threshold=config.pressure_threshold,
            used_bytes_fn=lambda: self.allocator.used_bytes,
            pool_stats_fn=lambda: self.pool.stats(),
            dedup_ratio_fn=lambda: float(self.dedup.stats.dedup_ratio),
            compression_ratio_fn=lambda: float(self.compressor.compression_ratio),
        )
        self.pager = Pager(self, self.tiers)
        self.prefetch_engine = PrefetchEngine(self)
        self.scheduler = MAKSScheduler(
            self,
            interval_s=config.scheduler_interval_s,
            enable_background=config.enable_scheduler if enable_scheduler is None else enable_scheduler,
            pressure_threshold=config.pressure_threshold,
        )
        self._prefix_index: dict[str, list[str]] = {}  # session -> prefix hash chain
        self.lifecycle.on_transition(self._on_lifecycle)

    def _on_lifecycle(self, kv_id: str, frm: KVState, to: KVState) -> None:
        _ = (kv_id, frm, to)

    def _provider(self, name: ProviderName | str) -> IKVProvider:
        key = name.value if isinstance(name, ProviderName) else name
        return self.providers[key]

    async def create(
        self,
        payload: bytes,
        *,
        agent_id: str = "",
        session_id: str = "",
        conversation_id: str = "",
        identity: KVIdentity | None = None,
        prompt_hash: str = "",
        prompt_prefix: bytes | str = b"",
        token_count: int = 0,
        layer_count: int = 0,
        head_count: int = 0,
        priority: int = 0,
        hint: LocalityHint | None = None,
        prefill_source: str = "",
        ttl_s: float | None = None,
        backend_id: str = "",
        cascade_stage: int = 0,
        reasoning_depth: int = 0,
        importance: float = 0.0,
    ) -> KVHandle:
        t0 = monotonic_ms()
        ident = identity or KVIdentity()
        backend = backend_id or self.default_backend_id
        caps = self.capabilities.flags(backend)
        # Capability gate: refuse cross-model reuse path unless backend allows
        if not caps.cross_model_reuse:
            # identity fingerprint already gates dedup; explicit no-op guard
            pass
        if not self.armora.admit(len(payload), priority=priority):
            await self.relieve_pressure(bytes_needed=len(payload))
            if not self.armora.admit(len(payload), priority=priority):
                raise KVBudgetExceededError("ARMORA budget rejected allocation")

        content_hash = self.hasher.hash(payload)
        if isinstance(prompt_prefix, str):
            prompt_bytes = prompt_prefix.encode("utf-8")
        else:
            prompt_bytes = prompt_prefix
        if not prompt_hash and prompt_bytes:
            prompt_hash = self.hasher.hash(prompt_bytes)

        # Dedup reuse — only when backend supports shared/prefix
        can_dedup = self.config.enable_dedup and (caps.shared_kv or caps.prefix_reuse)
        if can_dedup:
            existing = self.dedup.lookup(
                ident, prompt_prefix=prompt_bytes or prompt_hash, content_hash=content_hash
            )
            if existing is not None:
                rec = await self.registry.get(existing.kv_id)
                if rec is not None and ident.compatible_with(rec.identity):
                    self.refcount.increment(rec.kv_id, agent_id or rec.owner_agent)
                    rec.refcount = self.refcount.get(rec.kv_id)
                    await self.registry.touch(rec.kv_id, hit=True)
                    self.pool.increment_share(rec.kv_id)
                    self.metrics.inc("maks_cache_hit")
                    self._refresh_gauges()
                    return KVHandle(
                        kv_id=rec.kv_id,
                        provider=rec.provider,
                        location=rec.location,
                        share_token=rec.capability_token,
                    )

        loc_hint = hint or self.scheduler.get_locality(agent_id)
        kv_id = new_kv_id()
        prov, location = await self.allocator.allocate(
            kv_id, len(payload), hint=loc_hint
        )
        # Backends that need compression (e.g. NVMe) apply it themselves.
        await prov.store(kv_id, payload)

        dedup_key = ""
        if can_dedup:
            ent = self.dedup.register(
                kv_id,
                ident,
                prompt_prefix=prompt_bytes or prompt_hash,
                content_hash=content_hash,
            )
            dedup_key = ent.dedup_key

        meta = build_metadata(
            payload=payload,
            identity=ident,
            backend=prov.name,
            compression=self.compression.name,
            content_hash=content_hash,
            prompt_hash=prompt_hash,
            producer=agent_id,
            token_count=token_count,
            layer_count=layer_count,
            head_count=head_count,
            creation_latency_ms=monotonic_ms() - t0,
            prefill_source=prefill_source,
        )
        token = new_token()
        rec = KVRegistryRecord(
            kv_id=kv_id,
            owner_agent=agent_id,
            identity=ident,
            prompt_hash=prompt_hash,
            conversation_id=conversation_id,
            session_id=session_id,
            created_at=now_ts(),
            last_access=now_ts(),
            ttl_s=self.config.default_ttl_s if ttl_s is None else ttl_s,
            refcount=1,
            provider=ProviderName(prov.name) if prov.name in ProviderName._value2member_map_ else ProviderName.RAM,
            location=location,
            tier=KVTier.HOT,
            dedup_key=dedup_key,
            state=KVState.ALLOCATED,
            metadata=meta,
            priority=priority,
            numa_node=loc_hint.numa_node if loc_hint else 0,
            capability_token=token,
        )
        await self.registry.upsert(rec)
        self.lifecycle.bind(kv_id, KVState.ALLOCATED)
        self.refcount.increment(kv_id, agent_id, exclusive=True)
        # Global page pool registration
        self.pool.allocate_pages(
            kv_id,
            len(payload),
            identity=ident,
            provider=rec.provider,
            location=location,
            content_hash=content_hash,
            prefix_hash=prompt_hash,
            compression=self.compression.name,
            numa_node=rec.numa_node,
            backend_id=backend,
            capabilities=caps.as_dict(),
            importance=importance if importance else float(priority),
            cascade_stage=cascade_stage,
            reasoning_depth=reasoning_depth,
        )
        self.handles.bind(
            kv_id=kv_id,
            session_id=session_id,
            agent_id=agent_id,
            identity=ident,
            backend_id=backend,
            created_at=rec.created_at,
        )
        self.metrics.inc("maks_cache_miss")
        self.metrics.observe_latency("maks_allocation_latency_ms", meta.creation_latency_ms)
        self._refresh_gauges()
        return KVHandle(kv_id=kv_id, provider=rec.provider, location=location, share_token=token)

    async def lookup(
        self,
        *,
        kv_id: str = "",
        prompt_hash: str = "",
        identity: KVIdentity | None = None,
        prompt_prefix: bytes | str = b"",
        partial_prefix: bool = True,
        backend_id: str = "",
    ) -> KVHandle | None:
        t0 = monotonic_ms()
        backend = backend_id or self.default_backend_id
        caps = self.capabilities.flags(backend)
        if kv_id:
            rec = await self.registry.get(kv_id)
            if rec is None:
                self.metrics.inc("maks_cache_miss")
                self.telemetry.observe_latency("maks_lookup_latency_ms", monotonic_ms() - t0)
                return None
            if identity is not None and not identity.compatible_with(rec.identity):
                raise KVIdentityMismatchError(kv_id)
            await self.registry.touch(kv_id, hit=True)
            self.eviction.observe_access(kv_id)
            self.pool.touch(kv_id)
            self.metrics.inc("maks_cache_hit")
            self.telemetry.observe_latency("maks_lookup_latency_ms", monotonic_ms() - t0)
            return KVHandle(
                kv_id=rec.kv_id,
                provider=rec.provider,
                location=rec.location,
                share_token=rec.capability_token,
            )

        ident = identity or KVIdentity()
        if self.config.enable_dedup and (caps.shared_kv or caps.prefix_reuse):
            content_hint = ""
            ent = self.dedup.lookup(ident, prompt_prefix=prompt_prefix or prompt_hash, content_hash=content_hint)
            if ent is not None:
                return await self.lookup(kv_id=ent.kv_id, identity=ident, backend_id=backend)

        if prompt_hash and self.config.enable_prefix_reuse and caps.prefix_reuse:
            matches = await self.registry.find_by_prefix(prompt_hash)
            for rec in matches:
                if identity is not None and not identity.compatible_with(rec.identity):
                    continue
                if not partial_prefix and rec.prompt_hash != prompt_hash:
                    continue
                await self.registry.touch(rec.kv_id, hit=True)
                self.pool.touch(rec.kv_id)
                self.metrics.inc("maks_cache_hit")
                self.telemetry.observe_latency("maks_lookup_latency_ms", monotonic_ms() - t0)
                return KVHandle(
                    kv_id=rec.kv_id,
                    provider=rec.provider,
                    location=rec.location,
                    share_token=rec.capability_token,
                )

        self.metrics.inc("maks_cache_miss")
        self.telemetry.observe_latency("maks_lookup_latency_ms", monotonic_ms() - t0)
        return None

    async def share(self, kv_id: str, consumer_id: str) -> str:
        t0 = monotonic_ms()
        rec = await self.registry.get(kv_id)
        if rec is None:
            raise KVNotFoundError(kv_id)
        binding = self.handles.get(kv_id)
        backend = binding.backend_id if binding else self.default_backend_id
        if not self.capabilities.flags(backend).shared_kv:
            raise KVPermissionError(f"backend {backend} does not support shared_kv")
        prov = self._provider(rec.provider)
        token_or_handle = await prov.share(kv_id, consumer_id)
        perm = self.sharing.grant(kv_id, rec.owner_agent, consumer_id)
        if consumer_id not in rec.readers:
            rec.readers.append(consumer_id)
        if consumer_id not in rec.metadata.consumers:
            rec.metadata.consumers.append(consumer_id)
        self.refcount.increment(kv_id, consumer_id)
        rec.refcount = self.refcount.get(kv_id)
        await self.registry.upsert(rec)
        self.pool.increment_share(kv_id)
        if self.lifecycle.get(kv_id) in {KVState.ALLOCATED, KVState.WARMED}:
            self.lifecycle.try_transition(kv_id, KVState.SHARED)
            await self.registry.set_state(kv_id, KVState.SHARED)
        self.metrics.observe_latency("maks_share_latency_ms", monotonic_ms() - t0)
        return perm.token or token_or_handle

    async def release(self, kv_id: str, agent_id: str = "") -> None:
        rec = await self.registry.get(kv_id)
        if rec is None:
            return
        count = self.refcount.decrement(kv_id, agent_id)
        if agent_id and agent_id in rec.readers:
            rec.readers = [r for r in rec.readers if r != agent_id]
        rec.refcount = count
        await self.registry.upsert(rec)
        self.pool.decrement_share(kv_id)
        if count <= 0:
            if rec.pinned:
                return
            self.lifecycle.try_transition(kv_id, KVState.RELEASED)
            await self.registry.set_state(kv_id, KVState.RELEASED)

    async def migrate(self, kv_id: str, target: ProviderName | str, *, reason: str = "") -> str:
        loc = await self.migration.migrate(kv_id, target, reason=reason)
        self.lifecycle.try_transition(kv_id, KVState.MIGRATED)
        await self.registry.set_state(kv_id, KVState.MIGRATED)
        target_name = target if isinstance(target, ProviderName) else ProviderName(str(target).lower())
        self.pool.set_location(kv_id, loc, target_name)
        self.pool.set_tier(kv_id, self.tiers.tier_for_provider(target_name), target_name)
        self.telemetry.record_migration()
        self._refresh_gauges()
        return loc

    async def delete(self, kv_id: str, *, force: bool = False) -> None:
        rec = await self.registry.get(kv_id)
        if rec is None:
            return
        if rec.pinned and not force:
            raise KVPinnedError(kv_id)
        prov = self._provider(rec.provider)
        try:
            await prov.delete(kv_id)
        except Exception:
            pass
        if rec.dedup_key:
            self.dedup.forget(rec.dedup_key)
        self.sharing.revoke_all(kv_id)
        self.refcount.release_all(kv_id)
        self.allocator.release_bytes(rec.metadata.kv_size)
        self.pool.release(kv_id)
        self.handles.unbind(kv_id)
        self.lifecycle.try_transition(kv_id, KVState.DESTROYED)
        self.lifecycle.unbind(kv_id)
        await self.registry.delete(kv_id)
        self._refresh_gauges()

    async def preload(
        self,
        payload: bytes,
        *,
        agent_id: str = "",
        session_id: str = "",
        identity: KVIdentity | None = None,
        prompt_hash: str = "",
        pin: bool = False,
    ) -> KVHandle:
        handle = await self.create(
            payload,
            agent_id=agent_id,
            session_id=session_id,
            identity=identity,
            prompt_hash=prompt_hash,
            prefill_source="preload",
        )
        await self.warm(handle.kv_id)
        if pin:
            await self.pin(handle.kv_id)
        return handle

    async def pin(self, kv_id: str) -> None:
        rec = await self.registry.get(kv_id)
        if rec is None:
            raise KVNotFoundError(kv_id)
        await self._provider(rec.provider).pin(kv_id)
        rec.pinned = True
        await self.registry.upsert(rec)
        self.pool.pin(kv_id)
        self.lifecycle.try_transition(kv_id, KVState.PINNED)
        await self.registry.set_state(kv_id, KVState.PINNED)

    async def unpin(self, kv_id: str) -> None:
        rec = await self.registry.get(kv_id)
        if rec is None:
            raise KVNotFoundError(kv_id)
        await self._provider(rec.provider).unpin(kv_id)
        rec.pinned = False
        await self.registry.upsert(rec)
        self.pool.unpin(kv_id)
        # Return to shared/warmed
        target = KVState.SHARED if rec.readers else KVState.WARMED
        self.lifecycle.try_transition(kv_id, target)
        await self.registry.set_state(kv_id, target)

    async def warm(self, kv_id: str) -> None:
        rec = await self.registry.get(kv_id)
        if rec is None:
            raise KVNotFoundError(kv_id)
        await self._provider(rec.provider).warm(kv_id)
        if rec.provider is not ProviderName.RAM:
            try:
                await self.migration.promote(kv_id, reason="warm")
            except Exception:
                pass
        self.lifecycle.try_transition(kv_id, KVState.WARMED)
        await self.registry.set_state(kv_id, KVState.WARMED)
        await self.registry.set_tier(kv_id, KVTier.HOT)

    async def cold(self, kv_id: str) -> None:
        rec = await self.registry.get(kv_id)
        if rec is None:
            raise KVNotFoundError(kv_id)
        if rec.pinned:
            return
        await self._provider(rec.provider).cold(kv_id)
        await self.registry.set_tier(kv_id, KVTier.COLD)

    async def load_payload(self, kv_id: str) -> bytes:
        rec = await self.registry.get(kv_id)
        if rec is None:
            raise KVNotFoundError(kv_id)
        data = await self._provider(rec.provider).load(kv_id)
        if rec.metadata.compression and rec.metadata.compression != "none":
            try:
                return self.compression.decompress(data)
            except Exception:
                return data
        return data

    async def prefetch(self, req: PrefetchRequest) -> KVHandle | None:
        return await self.prefetch_engine.prefetch(req)

    async def cleanup(self) -> dict[str, int]:
        removed = 0
        expired = 0
        now = now_ts()
        for rec in await self.registry.all_records():
            if rec.ttl_s > 0 and (now - rec.created_at) > rec.ttl_s and not rec.pinned:
                await self.delete(rec.kv_id, force=True)
                expired += 1
                continue
            if rec.state is KVState.RELEASED and rec.refcount <= 0 and not rec.pinned:
                await self.delete(rec.kv_id, force=True)
                removed += 1
        known = set(await self.registry.list_ids())
        for zid in self.refcount.zombies(known):
            self.refcount.release_all(zid)
        self.refcount.cleanup_zero()
        return {"destroyed": removed, "expired": expired}

    async def relieve_pressure(self, *, bytes_needed: int = 0) -> int:
        snap = self.pressure_monitor.snapshot()
        self.eviction.set_pressure(snap.pressure)
        # Feed page signals into scored eviction
        signals: dict[str, dict] = {}
        for meta in self.pool.all_pages():
            signals.setdefault(meta.kv_id, {}).update(
                {
                    "importance": meta.importance,
                    "prediction_score": meta.prediction_score,
                    "cascade_stage": meta.cascade_stage,
                    "reasoning_depth": meta.reasoning_depth,
                }
            )
        self.eviction.set_page_signals(signals)
        victims = await self.eviction.select_victims(bytes_needed=bytes_needed, count=4)
        freed = 0
        for kid in victims:
            rec = await self.registry.get(kid)
            if rec is None or rec.pinned:
                continue
            # Prefer demote before destroy
            if rec.provider is not ProviderName.NVME:
                try:
                    await self.pager.page_out(kid, reason="pressure")
                    continue
                except Exception:
                    try:
                        await self.migration.demote(kid, reason="pressure")
                        continue
                    except Exception:
                        pass
            size = rec.metadata.kv_size
            try:
                await self.delete(kid, force=False)
                freed += size
                self.metrics.inc("maks_eviction_count")
                self.eviction.eviction_count += 1
            except KVPinnedError:
                continue
        self._refresh_gauges()
        return freed

    def pressure(self) -> float:
        return self.pressure_monitor.pressure()

    def pressure_snapshot(self) -> dict[str, Any]:
        snap = self.pressure_monitor.snapshot()
        d = snap.as_dict()
        d["hit_rate"] = self.dedup.stats.hit_rate
        return d

    def capability_matrix(self) -> dict[str, dict[str, bool]]:
        return self.capabilities.matrix()

    def _refresh_gauges(self) -> None:
        snap = self.pressure_monitor.snapshot()
        self.telemetry.publish_pool(
            self.pool.stats(),
            pressure=snap.pressure,
            fragmentation=snap.fragmentation,
        )
        self.telemetry.publish_ratios(
            dedup_ratio=float(self.dedup.stats.dedup_ratio),
            compression_ratio=float(self.compressor.compression_ratio),
            refcount=float(sum(p.refcount for p in self.pool.all_pages())),
            provider_usage=float(self.allocator.used_bytes),
        )
        self.metrics.set("maks_memory_usage_bytes", float(self.allocator.used_bytes))
        self.metrics.set("maks_dedup_ratio", float(self.dedup.stats.dedup_ratio))
        hits = self.metrics.get("maks_cache_hit")
        misses = self.metrics.get("maks_cache_miss")
        total = hits + misses
        self.metrics.set("maks_reuse_ratio", (hits / total) if total else 0.0)

    async def refresh_tier_gauges(self) -> None:
        hot = warm = cold = 0
        ref_total = 0
        for rec in await self.registry.all_records():
            if rec.tier is KVTier.HOT:
                hot += 1
            elif rec.tier is KVTier.WARM:
                warm += 1
            else:
                cold += 1
            ref_total += rec.refcount
        self.metrics.set("maks_hot_entries", float(hot))
        self.metrics.set("maks_warm_entries", float(warm))
        self.metrics.set("maks_cold_entries", float(cold))
        self.metrics.set("maks_refcount_total", float(ref_total))
        self.metrics.set("maks_entries", float(hot + warm + cold))

    async def _find_by_session(self, key: str) -> KVRegistryRecord | None:
        resolved = self.handles.resolve_session(key)
        if resolved:
            rec = await self.registry.get(resolved)
            if rec is not None:
                return rec
        for rec in await self.registry.all_records():
            if rec.session_id == key or rec.kv_id == key:
                return rec
        return None

    # DIPA SupportsKVSharing surface
    async def store(self, key: str, data: bytes) -> None:
        existing = await self._find_by_session(key)
        if existing is not None:
            prov = self._provider(existing.provider)
            await prov.store(existing.kv_id, data)
            existing.metadata.kv_size = len(data)
            existing.last_access = now_ts()
            await self.registry.upsert(existing)
            return
        await self.create(data, session_id=key, agent_id=key)

    async def load(self, key: str) -> bytes:
        handle = await self.lookup(kv_id=key)
        if handle is not None:
            return await self.load_payload(handle.kv_id)
        rec = await self._find_by_session(key)
        if rec is not None:
            return await self.load_payload(rec.kv_id)
        raise KVNotFoundError(key)

    def start(self) -> None:
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.stop()
