# Component Mapping — Requested Names → Repo

| Requested | Status | Path |
|-----------|--------|------|
| `SGLangBackend` | Implemented (HTTP + PD client) | `neuroswarm_arm/runtime/dipa/backends/sglang/` |
| `LlamaCppBackend` | Extended for PD | `neuroswarm_arm/runtime/dipa/backends/llama_cpp/` |
| `BackendRegistry` | Existing | `backends/registry.py` |
| `BackendCapabilities` | Extended | `interfaces/types.py` |
| `BackendFactory` | New | `backends/factory.py` |
| `RuntimeManager` | Alias of `DIPARuntime` + lifecycle | `kernel.py`, `control/lifecycle_manager.py` |
| `PrefillManager` | New | `pd/prefill_manager.py` |
| `DecodeManager` | New | `pd/decode_manager.py` |
| `PrefixCacheManager` | New | `cache/prefix_cache_manager.py` |
| `KVTransferManager` | New | `pd/kv_transfer.py` |
| `BatchScheduler` | New facade | `pd/batch_scheduler.py` |
| `ChunkPlanner` | New | `pd/chunk_planner.py` |
| `ChunkExecutor` | New | `pd/chunk_executor.py` |
| `WarmupManager` | Existing + prefix warm | `control/warmup_manager.py` |
| `MetricsCollector` | Existing + PD metrics | `control/metrics_collector.py`, `telemetry/metrics.py` |
| `HealthService` | Existing + PD readiness | `control/health_service.py` |

## Interface protocols

| Protocol | Path |
|----------|------|
| `IPrefillRuntime` | `interfaces/pd.py` |
| `IDecodeRuntime` | `interfaces/pd.py` |
| `IKVTransfer` | `interfaces/pd.py` |
| `IPrefixCache` | `interfaces/pd.py` |
| `IChunkPlanner` | `interfaces/pd.py` |

## Frozen upper-layer contracts

| Layer | Contract |
|-------|----------|
| ARMORA | `IInferenceEngine` |
| HAOE | `handle()` / `SupportsInference` |
| AQR | `IQuantConnector` |
| AWPP | `IWarmConnector` |
| MAKS | `IKVCacheConnector` |
| RTG | `IReasoningHook` |
