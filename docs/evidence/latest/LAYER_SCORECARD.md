# Layer scorecard (honest status)

Source: code audit + `MEASURED.md` + Prometheus capture (2026-07-25).

| Layer | Status | Notes |
|-------|--------|-------|
| **ASCR / speculative cascade** | PARTIAL | App-level quality cascade works; native `tier-spec` in-process spec for measured gain |
| **Native llama.cpp spec (`tier-spec`)** | PASS (when deployed) | `--spec-type draft-simple` + Qwen 0.5B draft / 3B target |
| **RTG reasoning governor** | PARTIAL | L0–L3 policies live; streaming `</think>` injection on `stream=true` |
| **Semantic MCP router** | PASS | 83.3% top-1, 16% avg token reduction, 6 tools |
| **KleidiAI build** | PASS | `GGML_CPU_KLEIDIAI=ON`; +26–64% measured on Axion |
| **Performix** | PASS | `code_hotspots` + instruction mix via `performix-bridge` |
| **NUMA-split** | N/A | 1 NUMA node on c4a-standard-8 — cache-aware cpuset only |
| **SGLang PD** | OFF | Stub present; `NSA_DIPA_PD_MODE=off` |
| **GSM8K/HumanEval RTG accuracy** | PARTIAL | `benchmarks/governor_accuracy.py` |
| **MAKS / Multi-Agent KV Sharing** | PARTIAL | Memory OS tested; MTE + 2× agents Marketing-only |

Do **not** headline unmeasured 1.8–2.3× or 40–60% accuracy delta until gates in `docs/armcascade/benchmark.md` pass.

**Verdict key:** **PASS** = measured + wired on Axion · **PARTIAL** = code live, gaps or no live bench · **Marketing-only** = pitch claim, not shippable on Axion today · **FAIL** = broken or absent

## 8. MAKS — Multi-Agent KV Sharing

| Capability | Verdict | Rationale |
|------------|---------|-----------|
| Memory OS (dedup, page pool, sharing, migration, DIPA connector) | **PARTIAL** | `KVManager` + pool + sharing implemented and tested; live swarm dedup bench not wired yet |
| ARM MTE zero-copy sharing | **Marketing-only** | Stub backend; no user-space MTE on Axion |
| 2× concurrent agents (pitch claim) | **Marketing-only** | No measured `concurrent_agents_supported` until bench lands |

### Code refs

| File | Lines | Role |
|------|-------|------|
| `neuroswarm_arm/runtime/maks/manager.py` | 678 | `KVManager`: create/share/dedup/migrate/telemetry |
| `neuroswarm_arm/runtime/maks/pool.py` | 275 | Global page pool, refcount, CoW |
| `neuroswarm_arm/runtime/maks/sharing.py` | 85 | `SharingEngine` grants/revokes |
| `neuroswarm_arm/runtime/maks/backends/future_mte_backend.py` | stub | `AVAILABLE=False` |

### MTE honesty (do not claim shipping)

MTE native shim raises `NotImplementedError` (`native/mte/__init__.py`); `FutureMTEBackend` raises `KVProviderUnavailableError` on all ops (`backends/future_mte_backend.py`); AQR feature detector reports `mte=UNAVAILABLE` (`aqr/hardware/profiler.py`); Axion `/proc/cpuinfo` has no MTE flag (`01-axion-system-info.txt`). `future_mte` is a feature-flag placeholder for AmpereOne / Orion-O6 / future Graviton — **not shipping on GCP Axion**.

Do **not** claim: MTE shipping; 2× concurrent agents; CXL sub-µs wins (see `docs/maks/axion-compatibility.md`).

### Tests (`tests/runtime/maks/`)

`uv run pytest tests/runtime/maks -q` → **38 passed** (2026-07-25).

`test_integration.py` (7): `test_dipa_connector_roundtrip`, `test_dipa_connector_q8_compression`, `test_identity_mismatch_no_blind_share`, `test_concurrent_creates`, `test_refcount_race`, `test_pressure_relief`, `test_sqlite_registry_persist`

`test_mte_backend.py` (6): `test_mte_available_allocate_store_load`, `test_mte_unavailable_raises`, `test_mte_unavailable_hwcap2_unset`, `test_tag_grant_flow`, `test_grant_mte_revoke_clears_tag`, `test_feature_matrix_reflects_mte`

`test_q8_codec.py` (7): `test_f32_roundtrip_cosine[64|768|4096]`, `test_per_block_symmetric_no_zero_point`, `test_compression_ratio_f32_vectors`, `test_byte_roundtrip`, `test_v1_backward_compat`

`test_unit.py` (18): `test_hasher_identity_differs_by_quant`, `test_lifecycle_transitions`, `test_refcount_orphan_zombie`, `test_create_share_release`, `test_dedup_reuse`, `test_pin_blocks_delete`, `test_migrate_ram_to_mmap`, `test_prefix_lookup`, `test_mte_unavailable`, `test_page_pool_registers_on_create`, `test_scored_eviction_default`, `test_capability_matrix_no_cross_model`, `test_connector_capability_surface`, `test_s3fifo_policy_selects_victims`, `test_q8_codec_roundtrip`, `test_semantic_cache_minhash_hit`, `test_pressure_monitor_unified`, `test_cow_share_increments_pool`

Key honesty signals: `test_mte_unavailable`, `test_dedup_reuse`, `test_concurrent_creates`.

### Benchmark evidence

| Artifact | Status |
|----------|--------|
| `docs/evidence/latest/layer-verify/14-maks-dedup.json` | **PENDING** — `benchmarks/maks_multi_agent_dedup_bench.py` + `scripts/layer-live-verify.sh` step 14 not wired yet; do not fabricate `dedup_savings_pct` or `concurrent_agents_supported` |
| `prometheus-metrics.txt` `maks_dedup_ratio` (~0.68) | Runtime scrape only — not a multi-agent swarm bench |

## Smoke blockers

- `14-maks-dedup.json` missing — multi-agent dedup bench not wired into layer-verify
- MTE zero-copy and 2× concurrent agents remain **Marketing-only** until bench + hardware path exist
- Do not headline MAKS dedup/concurrency wins in pitch until `14-maks-dedup.json` is captured on Axion
