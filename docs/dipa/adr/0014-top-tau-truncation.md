# ADR 0014: Top-τ Truncation Acceptance

## Status

Accepted

## Context

Target forward paths expose only top-N logprobs (`NSA_ASCR_LOGITS_TOP_N`). When a draft token falls outside that truncated set, Leviathan cannot compute `exp(q-p)` because `q` is unknown. Blind reject under-utilizes high-confidence drafts; blind accept compounds errors on later positions.

## Decision

1. When draft token is **not** in target top-N and `tau_floor > 0`, accept iff `p_draft = exp(min(0, draft_logprob)) >= tau_floor`.
2. On tau-accept: accept this position only, set `bonus_token` to target top-1, **break** the prefix (no further draft tokens this round).
3. Default `strategies.logits.tau_floor: 0.0` / `NSA_ASCR_TAU_FLOOR=0.0` keeps bit-exact Leviathan (rule 1 lossless). Non-zero tau is an explicit, env-gated relaxation.
4. Track `result.metrics["top_tau_used"]` and `LeviathanAcceptResult.top_tau_used`.

## Consequences

- Truncation false-rejects shrink when operators raise `NSA_ASCR_TAU_FLOOR`.
- Non-compounding + target top-1 bonus limits error drift after a relaxed accept.
- Default off → no distribution change for production lossless mode.
