# Extending MAKS for ARM MTE and CXL

MAKS keeps a stable `IKVProvider` ABI. Hardware backends plug in **without** changing `KVManager`, registry, dedup, or DIPA connectors.

## Steps to add a real MTE provider

1. Implement `IKVProvider` in `backends/future_mte_backend.py` (replace stub).
2. Set `AVAILABLE = True` only when feature detector reports MTE.
3. Map `share()` to tag-checked zero-copy mapping (`agent_id` → tag).
4. Register in `build_default_backends()` (already keyed as `future_mte`).
5. Gate selection: refuse if `AVAILABLE=False` (already raises `KVProviderUnavailableError`).

Suggested ops:

- `allocate` — tagged page pool
- `share` — increment tag / grant foreign read
- `pin` — pin tagged region against reclaim

## Steps to add a real CXL provider

1. Implement `IKVProvider` in `backends/future_cxl_backend.py`.
2. Use CXL.mem pool or RDMA-emulated pool URL from config.
3. Prefer as cold tier after NVMe when latency SLO allows.
4. Migration engine already demotes `RAM → mmap → redis → nvme`; insert CXL in policy order when live.

## API stability guarantee

These remain stable across SharedMemory → MTE → CXL:

- `KVManager.create/share/lookup/release/migrate/pin/unpin/preload`
- `IKVCacheConnector` (DIPA)
- `KVIdentity` fingerprint fields
- Prometheus `maks_*` metric names

Internal provider keys may grow; callers use `ProviderName` enum / string names.
