# Layer 1 — Token-level speculative decoding

Judges: read this in ~60 seconds.

## Architecture

```text
  draft (tier1 / 0.5B)  --model-draft-->  llama-server (tier-spec :8084)
                                              |  --model = tier2 3B target
                                              |  native draft-simple
                                              v
  A/B baseline (tier2 3B, no draft)  <--- compare tok/s --->  tier-spec
  ASCR verify (top-τ G14 + n-gram G13) when NSA_TIER_SPEC_URL set
```

- **tier-spec** runs `llama-server` with `--model` + `--model-draft` (same GGUF OK when a separate draft is unavailable).
- Gateway sets `NSA_TIER_SPEC_URL=http://tier-spec:8080` so DIPA forwards `n_probs` for Leviathan verification.
- A/B bench: `python benchmarks/spec_decode_native.py --rounds 3` (spec :8084 vs baseline tier2 :8082).

## A/B table

Latest run: `run_20260802T112941Z.json` (Axion, median of 3 rounds):

| arm | url | tok/s (median) | latency_ms_mean | completion_tokens |
|---|---|---:|---:|---:|
| tier-spec-draft-simple | `http://127.0.0.1:8084` | 11.787 | 3105.74 | 319 |
| tier2-no-spec | `http://127.0.0.1:8085` | 8.237 | 4388.94 | 321 |

**measured_speedup:** 1.431× (3B target + 0.5B draft vs 3B alone). Same-GGUF self-draft regresses (~0.5×) — use a real smaller draft.

## Prometheus / ASR counters

| metric | type | meaning |
|---|---|---|
| `asr_draft_tokens_total` | counter | Draft tokens proposed into the verify loop |
| `asr_accepted_tokens_total` | counter | Draft tokens accepted by top-τ / Leviathan |
| `asr_verify_calls_total` | counter | Calls into `accept_one_draft_position` (or `record_spec_verify`) |
| `asr_tok_per_s` | gauge | EWMA of accepted tokens / wall time |

## Basis

Leviathan et al. 2023 *Fast Inference from Transformers via Speculative Decoding*; Chen et al. 2023 *Accelerating Large Language Model Decoding with Speculative Sampling*.
