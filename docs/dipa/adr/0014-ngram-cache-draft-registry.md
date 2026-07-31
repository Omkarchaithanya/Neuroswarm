# 0014 — N-gram Cache + Draft Model Registry

**Status:** Accepted  
**Date:** 2026-07-31  
**Deciders:** Neuroswarm ARM/DIPA team  

## Context

`SelfSpeculationProposer` / `NgramProposer` echoed the trailing n-gram without
searching prompt history. Proper Prompt Lookup Decoding needs either an O(N)
scan per propose or an O(1) continuation table. Separately, `DraftModelProposer`
always used `tier1` regardless of target model or host arch (Axion vs Apple).

## Decision

1. **`NgramCache`**: Build a sliding-window `(n-1)-gram → [next_token, …]` dict
   (survey-style n-gram cache; not a literal suffix array). Lazy build on first
   propose; rebuild on `context_shift` when the trailing K tokens change by more
   than K relative to the previous call. Lookup O(1); fall back to linear seed
   scan; then legacy seed-echo.

2. **Gates**: `strategies.ngram_cache.enabled` (default false) and
   `NSA_NGRAM_CACHE`. Safe default keeps old echo/scan path behaviour when off.

3. **`DraftModelRegistry`**: Hardcoded `(target, host_arch) → (draft, quant)`
   pairs with config overlay. `detect_host_arch()` uses `NSA_HOST_ARCH`, Darwin
   `hw.model`, or `probe_cpu_features()` (SME2 → neoverse-v3, Axion →
   neoverse-v2).

4. **Draft resolve order**: `NSA_DRAFT_MODEL_PATH` → registry when
   `draft_registry` / `NSA_DRAFT_REGISTRY_AUTO` → else `tier1`. Identity stored
   in proposal metadata; does not alter lossless acceptance (ngram/suffix already
   allowed to relax; draft_model still verified by target).

## Consequences

- O(1) n-gram lookup after build; evidence in
  `docs/evidence/latest/layer-verify/15-ngram-cache.txt`.
- Reversible: both features default off in `strategies.yaml`.
- No new heavy deps; ARM-TRUTHY host detection reuses KleidiAI probe.
