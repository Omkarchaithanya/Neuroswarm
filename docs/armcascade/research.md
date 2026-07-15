# ASCR Research Summary

**Adaptive Speculative Cascade Runtime (ASCR)** — ArmCascade throughput engine for NEXUS-ARM on GCP Axion (Neoverse V2).

This document compares speculative decoding systems and records design decisions for ASCR. It is a reference, not a mandate to copy any single upstream.

## Design principle

No algorithm is universally best. Modern stacks (llama.cpp, SGLang, vLLM) expose multiple speculative modes behind configurable runtimes. ASCR selects strategy, draft length, verification mode, acceptance policy, and escalation graph from workload + telemetry + peer-layer signals.

## Comparison matrix

| System | Advantage | Limitation | Runtime cost | Memory | ARM/CPU fit | Integration |
|--------|-----------|------------|--------------|--------|-------------|-------------|
| **llama.cpp draft+target** | Mature CPU path; KleidiAI; `--draft` / server draft | Needs second GGUF; HTTP server logits limited | Draft + 1 verify forward | 2 model footprints | Excellent (KleidiAI) | ProcessSupervisor + ASCR loop |
| **llama.cpp self-spec / n-gram** | No draft model; strong on repetitive agent prompts | Weak on high-entropy reasoning | Near-zero draft | N-gram map only | Excellent | Working ASCR proposer |
| **SGLang speculative** | Native kernels, batching, radix | Must not duplicate (ADR-0007) | Server-side | Engine-owned | Good on Arm64 CPU engine | Encapsulate behind HAL |
| **EAGLE / EAGLE-3** | High accept rate via feature-level draft | Needs trained draft head; GPU-centric literature | Extra head forward | Draft head weights | Moderate until ARM ports mature | Plugin stub → future |
| **P-EAGLE / Parallel EAGLE** | Parallel draft paths | Complexity + mem | Higher | Higher | Future | Plugin stub |
| **Medusa** | Multi-head tree draft on target | Training + tree verify | Multi-head | Extra heads | Moderate | Plugin stub |
| **PARD** | Parallel draft decoding | Research maturity | Medium | Medium | Future | Plugin stub |
| **Block / multi-token verify** | Amortizes target forward over K tokens | Needs logits or agreement proxy | 1 target pass / block | KV for block | Excellent for ASCR v1 | Working primary |
| **Tree verification** | Higher accept under branching drafts | Complex; logits required | Higher | Tree KV | Future | Plugin stub |
| **Hierarchical cascade** | Cheap draft → mid verify → large arbiter | Additive latency if naive full regen | Tiered | Multi-model | Core ArmCascade path | Escalation graphs |
| **vLLM speculative** | Production GPU/CPU serving | Not Axion default | Engine-side | Engine-owned | Future HAL | Stub capability |
| **Quality-only cascade** | Works without logits | **Not** speculative speedup | Full gen × tiers | Per-tier | Fallback honesty | Labeled metrics |

## SpecForge / SpecBench

Use SpecBench-style metrics: acceptance rate, mean accepted length, effective tok/s, TTFT, rejected tokens, speculation gain (= target forwards saved). ASCR exposes these as `ascr_*` metrics; do not conflate with `dipa_cascade_hit_rate` (tier-1 finish fraction).

## Google / Meta / Microsoft / NVIDIA literature (synthesis)

Shared lessons ASCR adopts:

1. **Dynamic depth** — fixed K wastes budget; adapt draft length to accept history + latency SLO.
2. **Verification batching** — amortize target cost; CPU benefits more than GPU relative.
3. **Acceptance ≠ argmax match alone** — fuse entropy, history, task type (Medusa/EAGLE papers; RTG alignment).
4. **Heterogeneous draft/target** — CPU-CPU cascade works when draft is much cheaper (DuoDecoding / CAS-Spec class results).
5. **Do not fake logits** — if server cannot return token probs, use quality-cascade mode and label metrics.

## ARM / Axion constraints

| Constraint | Implication |
|------------|-------------|
| Axion ≈ Neoverse V2, often single NUMA | No cross-node draft/verify split; affinity still useful |
| KleidiAI via llama.cpp | Keep ProcessSupervisor + `GGML_CPU_KLEIDIAI`; no in-process GGML in v1 |
| MTE / CXL UNAVAILABLE | Shared KV via MAKS metadata only; no zero-copy CXL claims |
| SGLang ↔ llama KV layout mismatch | PD stays `recompute` for hetero path |

## Alternative designs considered

| Alternative | Why rejected / deferred |
|-------------|-------------------------|
| Replace DIPA with ASCR as whole Layer 2 | Breaks ADR-0001; ASCR is throughput engine inside DIPA |
| Always EAGLE-3 | Needs trained heads; not Axion-default |
| Always self-spec only | Misses draft-model gains on factual/chat |
| Hardcoded linear Tier1→2→3 | Blocks Tool/Mem escalation graphs |
| Reimplement SGLang spec kernels | ADR-0007 |

## ASCR architecture decisions

1. **Plugin strategies** — `ProposalStrategy` / `VerifierStrategy`; register + YAML.
2. **Adaptive thresholds only** — no fixed accept τ as sole gate.
3. **Escalation as DAG** — policy graphs, not hardcoded linear ladder.
4. **RL ports** — `RLObservation` / `RLAction`; heuristic agent now, PPO later.
5. **Honest degradation** — logits missing → quality-cascade; metrics separated.
6. **Connectors only** — AQR/AWPP/MAKS/RTG/Performix never owned by ASCR (ADR-0003).

## Performance expectations

| Path | Expectation |
|------|-------------|
| Draft + block verify, accept ≥70% | ~1.5–2.3× effective tok/s (measure on Axion) |
| N-gram self-spec, repetitive prompts | Additional gain when patterns hit |
| Quality-only cascade | Cost/latency routing — not speculative speedup |
| Single-NUMA Axion | Affinity helps; no cross-NUMA claim |

## Future research

- EAGLE-3 draft heads quantized for ARM CPU
- Tree verify when logits API available on llama-server
- Performix → PPO threshold agent closed loop
- Same-engine SGLang speculative proposer behind HAL
- SpecBench CI gate on Axion nightlies
