# ADR 0005: Closed-loop AROP is rule-based — not PPO / GEPA-as-knobs / GRPO

## Status

Accepted

## Context

Fantasy docs and some Plane 5 scaffolding (`neuroswarm_arm/evolution/`) suggest PPO, online RL, GEPA, or GRPO might drive cascade thresholds. Judges and operators need an honest answer: **what ships**, **what is scaffold**, and **what Axion model sizes are correct**.

## Decision

1. **Shipping closed loop = [`neuroswarm_arm/arop/`](../../neuroswarm_arm/arop/) rule-based R0–R3 only** (Performix JSON → one clamped ASCR/RTG knob → dry-run default → >5% rollback).
2. **PPO / online RL are not implemented.** [`OfflineRLTrainer`](../../neuroswarm_arm/evolution/rl/experience_store.py) is a stub that delegates to an offline contextual bandit; there is no PPO loss, policy network, or online update loop.
3. **GRPO does not appear anywhere in this repository** and is out of scope. GRPO is an LLM finetuning method, not a cascade-threshold tuner; this stack does not finetune GGUFs at runtime.
4. **GEPA is text-only** (ADR [0004](0004-gepa-text-only.md)). It may evolve prompts under ApprovalGate; it must **not** be claimed as the cascade / hardware / quant optimizer.
5. **`neuroswarm_arm/evolution/` remains scaffolding** until actuation defects are fixed (wrong `ascr=` target in `main.py`, no `apply_rl_action` on `ASCREngine`, `HeuristicPolicyAgent` default, `run_forever` never started). Do not treat `/arop/*` + GEPA as a live RL closed loop on Axion today.
6. **Axion c4a-standard-8 cascade sizes stay small Q4 GGUFs** (see below). “Optimization” means KleidiAI + routing + rule knobs — not larger weights.

## Why (defensible to judges)

| Reason | Detail |
|--------|--------|
| Sample poverty | Single 8-vCPU VM yields tens of requests, not RL-scale trajectories |
| Auditability | One clamped param + rollback is reproducible; a neural policy is not |
| Official GEPA scope | Genetic-Pareto text evolution — not numeric ASCR knobs |
| Hackathon honesty | Prove Performix → rule tune → measure; do not invent AWPP/PPO training |

## Process if RL / GEPA are added later (ordered)

1. Keep rule-based AROP v1 as the ASCR knob control plane.
2. Fix evolution actuation (`cascade_engine`, `apply_rl_action`, `PolicyRegistryBackedAgent`, optional `NSA_AROP_LOOP` with canary 5%, auto_promote off).
3. Offline bandit on logged `(state, action, reward)` only — still not PPO.
4. GEPA in parallel for **prompts only** + ApprovalGate.
5. PPO / CQL / GRPO only after real reward signal, large offline datasets, and offline eval — **online** PPO/GRPO remains out of scope for the Axion 8-vCPU demo.

## Axion c4a-standard-8 model sizes (correct)

Pinned in [`docker-compose.yaml`](../../docker-compose.yaml) for single-NUMA 8 vCPU (32GB RAM; avoid BF16 SGLang + three large GGUFs — see [axion-optimization.md](../inference/axion-optimization.md)):

| Tier | Default model | Quant | Cpuset | Threads | Role |
|------|---------------|-------|--------|---------|------|
| tier1 | Qwen2.5-0.5B-Instruct | Q4_0 | 0–1 | 2 | Draft |
| tier2 | Qwen2.5-3B-Instruct | Q4_0 | 2–4 | 3 | Mid verify |
| tier3 | DeepSeek-R1-Distill-Qwen-7B (`TIER3_MODEL`) | Q4_0 | 5–7 | 3 | Hard / reasoning |

Optional: `TIER3_MODEL=Llama-3.2-8B-Instruct-Q4_K_M.gguf` — still ~8B Q4-class, **not** 13B/70B.

## Consequences

- AROP v1 docs and commit messages must not claim PPO, GRPO, or GEPA-as-knob-tuner.
- Deferred closed-loop wiring enables **rule/bandit actuation** via `ASCREngine.apply_rl_action` / `StaticPolicyAgent` and `main.py` → `cascade_engine` — **not** PPO training.
- `OfflineRLTrainer.train_ppo` / `train_grpo` raise `NotImplementedError` (code-level guard).
- Performix evidence and rule tuner remain the judge-facing closed-loop story.

## References

- [gepa.md](../gepa.md), ADR [0004](0004-gepa-text-only.md)
- [`neuroswarm_arm/arop/README.md`](../../neuroswarm_arm/arop/README.md)
- [`neuroswarm_arm/evolution/rl/offline_rl.py`](../../neuroswarm_arm/evolution/rl/offline_rl.py)
- [`docs/inference/axion-optimization.md`](../inference/axion-optimization.md)
