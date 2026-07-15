# RTG Hackathon Justification

## Flagship claim

AIM Pillar 4 is no longer a static token limiter. NEXUS ships a **Reasoning
Token Governor** — a peer runtime kernel that closed-loop controls CoT length
using tool confidence, KV pressure, SLO remaining, entropy/plateau detectors,
SW-UCB thresholds, and ARM Performix/PMU telemetry on GCP Axion.

## Evidence story for judges

1. Submit easy tool query → RTG early-commit (≤256 thinking tokens).
2. Submit hard reasoning query → higher budget + optional escalate.
3. Grafana: `rtg_early_exit_total`, `rtg_thinking_tokens`, budget remaining.
4. Benchmarks: No Governor | Fixed | Legacy Dynamic | Adaptive RTG.

## Differentiation

Most Cloud AI entries deploy a model. NEXUS shows **hardware-aware serving
control**: Axion CPU cascade + semantic MCP router + shared KV + RTG — cited
against DEER / REFRAIN / TALE and vLLM/llama.cpp thinking budgets.

## Future

- Train L3 PPO from Mem0 session profiles
- True per-token stream hooks when llama.cpp SSE exposes logprobs
- Energy joules from Performix recipes in FinOps dashboard
