# ADR 0011: SpecInfer Tree Verification

## Status

Accepted

## Context

Block/logits verifiers check a single linear draft. SpecInfer (Miao et al.,
ASPLOS 2024) and Sequoia (Chen et al., NeurIPS 2024) show one target forward
can verify a *tree* of draft tokens, roughly doubling effective draft length
at constant draft cost when branching > 1.

## Decision

1. Add `TokenTree` / `TreeBuilder` / `TreeAcceptor` in
   `verification/tree.py` implementing SpecInfer DFS accept
   (greedy argmax or stochastic `min(1, exp(q-p))`) plus bonus token.
2. Replace `TreeVerifier` stub with a real `@register_verifier("tree")`
   that flattens the tree, runs one target logits forward
   (`max_tokens = depth + 1`), and returns `VerifyMode.TREE`.
3. `DraftModelProposer` builds a width-capped tree when
   `req.metadata["branching"] > 1` and `strategies.tree.enabled` /
   `NSA_ASCR_TREE_ENABLED` allow it; branching==1 stays flat.
4. Lossless guarantee unchanged for the accepted path (same Leviathan
   ratio as linear logits). Reversible via `strategies.tree.enabled=false`.

## Consequences

- Effective draft length rises with branching without extra draft forwards
  proportional to leaves (draft still pays per expansion step).
- Requires target top-N logprobs wide enough for
  `max_branching * top_k_per_branch`.
- Legacy block/single_token/batched/quality/logits verifiers untouched.
