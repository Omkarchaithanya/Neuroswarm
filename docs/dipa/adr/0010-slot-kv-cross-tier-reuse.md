# ADR 0010: Cross-Tier Slot KV Reuse (G8)

## Status

Accepted

## Context

ASCR speculative cascade runs draft on tier1 (small model) and block-verify on tier2 (target model). Each verify call previously recomputed the full prompt KV on the verify llama-server, even when `kv_handle` and `id_slot` session binding were already available. For long contexts this dominated round latency and erased speculative speedup.

llama-server already exposes `/slots/{id}?action=save|restore` and `--slot-save-path` for on-disk slot persistence. NeuroSwarm had `SlotClient` wrappers but never wired them across draft → verify.

## Decision

1. Persist draft-server KV to a shared filename under `NSA_LLAMA_SLOT_DIR` after each draft `generate()` when `kv_handle` is set.
2. Before verify `generate()`, restore that file into the verify server's `id_slot`; after verify, save verify KV back to the same file for the next round.
3. Gate with `strategies.yaml` → `slot_kv_reuse.enabled` and `NSA_LLAMA_SLOT_KV_REUSE` (default on).
4. Propagate `id_slot` through `ProposalRequest` / `VerifyRequest` / `ExecutionContext` without changing `DraftModelProposer` public interface.
5. Use `SlotContext` (save source on enter, restore target on exit) for explicit cross-server transfers when both clients are available.

## Consequences

- Verify rounds 2+ skip full prompt prefill when slot file exists (lossless — acceptance unchanged).
- Docker deployments need a **shared** slot directory mount across tier1/tier2 containers; separate per-tier volumes do not work without a shared bind.
- Bare-metal `/tmp/neuroswarm-slots` works when both llama-server processes use the same `--slot-save-path` or absolute filenames.
- Reversible: set `slot_kv_reuse.enabled: false` or `NSA_LLAMA_SLOT_KV_REUSE=0` for legacy re-prefill behavior.
