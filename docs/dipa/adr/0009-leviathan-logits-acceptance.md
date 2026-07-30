# ADR 0009: Leviathan Logits Acceptance

## Status

Accepted

## Context

ASCR block verification compared word-split text prefixes and optionally matched completion token text from llama logprobs. That path does not implement lossless Leviathan stochastic acceptance (`min(1, exp(q-p))`) and cannot preserve the target distribution bit-exact. Text agreement reported `logits_available` without true accept math, blocking G2/G3/G4.

## Decision

1. Add dedicated `logits` verifier strategy (`LogitsAcceptanceVerifier`) registered as `logits`.
2. Target forward requests OpenAI `logprobs` + `top_logprobs` via `LlamaCppBackend.generate_with_logits`.
3. Acceptance uses Leviathan rule: greedy argmax at `temperature=0`, stochastic `min(1, exp(q-p))` otherwise, with optional top-τ fallback when draft cumulative mass ≥ `tau_floor`.
4. `block` verifier remains text-agreement proxy (`logits_available=false`); reversible via `strategies.logits.enabled` and `defaults.verify_strategy`.
5. `VerifyMode.LOGITS`, `LogitsBundle`, and `bonus_token` on `VerifyResult` expose accept outcome for downstream gaps.

## Consequences

- True speculative acceptance when llama-server returns top-N logprobs (`NSA_LLAMA_N_PROBS` / `generate_with_logits`).
- `accept_mode=2.0` metric distinguishes logits accept from text proxy (`0.0`) and interim logprob text match (`1.0`).
- Enables G2/G3/G4 without changing legacy `dipa/cascade/CascadeEngine`.
- Requires llama.cpp logprobs API; missing logits → quality-cascade fallback (ADR-0008 honesty).
