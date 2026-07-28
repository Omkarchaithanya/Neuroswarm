# RTG Deep Research Report

## Problem

Reasoning LLMs (DeepSeek-R1, Qwen3-Thinking, OpenAI o-series) allocate long CoT
traces even for trivial tool-routing queries. Static `max_tokens` caps waste
budget on hard tasks and overthink easy ones. NEXUS MVP shipped a pre-request
heuristic cap in `ReasoningGovernor` — useful for demos, insufficient as a
serving control plane.

## Literature (selected)

| Work | Year | Mechanism | RTG mapping |
|------|------|-----------|-------------|
| DEER (arXiv:2504.15895) | 2025 | Thought-transition trial answers + confidence gate | `EarlyExitEngine` / L1 detectors |
| REFRAIN (arXiv:2510.10103) | 2025 | Reflective redundancy + SW-UCB threshold bandit | `BanditThresholdPolicy` |
| TALE (ACL Findings 2025) | 2025 | Complexity → budget; token elasticity | `BudgetPredictor` |
| s1 / budget forcing | 2025 | Force min/max think via end tokens | hard `thinking_token_cap` + force-close |
| DeepSeek-R1 | 2025 | RL-emergent length; still overthinks | external RTG required for SLO/cost |
| vLLM thinking budget | 2025–26 | `thinking_token_budget` sampler | DIPA request cap field |
| llama.cpp reasoning budget | 2026 | `--reasoning-budget` / force-close msg | force-close message in config |

## Production systems

- **vLLM**: reasoning parsers + hard thinking budget at sample time.
- **llama.cpp server**: per-request thinking budget + close message.
- **SGLang**: catalogued in AQR; no DIPA backend yet — RTG remains backend-agnostic via hooks.
- **HF TGI**: length/stop sequences; no adaptive CoT controller → NEXUS differentiator.

## ARM / Axion

- Neoverse V2 (GCP Axion C4A): SVE2, I8MM, BF16, DotProd — KleidiAI INT4 paths in llama.cpp.
- Arm Performix: Topdown recipes → RTG `HardwareMonitor` (best-effort JSON snapshot).
- PMU: Axion-safe no-op when counters unavailable (ADR fallbacks).

## Design thesis

Treat reasoning allocation as an **OS-style closed-loop controller**:

1. Admit → predict budget (TALE)
2. Stream → observe entropy/confidence/KV/SLO/PMU
3. Decide → hierarchical L0–L3 policy
4. Act → continue / early-commit / rebudget / escalate / quant hint
5. Feedback → SW-UCB bandit (default live path) + optional offline PPO scaffold (`NSA_RTG_PPO=1`)

Do **not** own inference (DIPA), quant (AQR), KV (MAKS), or scheduling (HAOE).
RTG is AIM Pillar 4 peer kernel via `IReasoningHook`.

**Honesty:** “PPO enabled” means the L3 scaffold is compiled in and may be opted in —
live defaults are L0–L2 heuristics/bandit. Trained PPO weights are Phase 2.
