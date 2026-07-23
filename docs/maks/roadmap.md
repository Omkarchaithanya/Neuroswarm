# MAKS Roadmap — Shared Memory → MTE → CXL

```text
Phase 0 (now)     Memory OS on GCP Axion
                  Global page pool + scored eviction + capability matrix
                  RAM + shm / mmap / Redis / NVMe
                  Capability tokens (not MTE tags)
                  SQLite registry, AQR identity keys
                  Plane-2 pressure facade → MAKS

Phase 1           Hardened multi-node Redis registry
                  Prefix + segment matching
                  Live engine page-table bridges (llama.cpp slots) — session-to-slot bridge in DIPA

Phase 2           ARM MTE provider on hardware that exposes user-space MTE
                  Zero-copy cross-agent reads
                  Replace capability-token path when MTE AVAILABLE

Phase 3           CXL.mem / CXL.cache tier
                  Cold KV off host DRAM
                  200k-token session survival with CXL + NVMe fallback

Phase 4           Distributed MAKS across Axion fleet
                  Speculative prefetch from AWPP RL predictor
                  Quantized KV compression
```
## Non-breaking migration rule

Ship new providers behind `IKVProvider`. Never require callers to change Layer-5 method signatures. Feature-detect before advertising wins.
