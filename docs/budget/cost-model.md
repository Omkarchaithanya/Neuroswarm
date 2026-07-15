# Cost Model

## Interface

`ICostModel.project(op, hardware, cache_state) → ResourceProjection`

Projection carries p50 and p90 vectors across budget dimensions (primarily `cost_usd`, tokens, latency).

## Components

| Component | Inputs | Notes |
|-----------|--------|-------|
| Prefill | prompt tokens, $/tok_prefill or CPU-ms amortization | Includes uncached vs cache_read rates |
| Decode | E[completion], $/tok_decode | Higher burndown than prefill |
| Reasoning | thinking tokens | Separate ledger from completion |
| Cache write | cache_creation tokens × write multiplier | Anthropic-style ephemeral multipliers configurable |
| Cache read | cache_read tokens × read rate | Discounted |
| KV residency | bytes × time × $/byte-s | Opportunity cost of MAKS pages |
| Speculative | draft_cost + verify_cost − saved_decode | Net can be negative (savings) |
| Tools / MCP | fixed + variable + retry fan-out | Router `cost_usd` features |
| Retries / cascade | branching × residual | Prevents thrash |
| Planner overhead | fixed planner cost dim | `max_planner_cost` |

## Typed token vector

Billing uses distinct token classes (OpenAI/Anthropic lesson):

- `uncached_in`, `cache_write`, `cache_read`, `completion`, `reasoning`

Each class has a configurable unit price and burndown weight in `BudgetRuntimeConfig`.

## Reserve policy

ARMORA reserves at **p90**. Reconcile applies actual spend and records `budget_estimate_error{dim}`.

## Default rates

Defaults load from `NSA_BUDGET_*` / YAML — not from source constants. Example env keys:

| Env | Meaning |
|-----|---------|
| `NSA_BUDGET_USD_PER_1K_PROMPT` | Prompt $/1k |
| `NSA_BUDGET_USD_PER_1K_COMPLETION` | Completion $/1k |
| `NSA_BUDGET_USD_PER_1K_REASONING` | Reasoning $/1k |
| `NSA_BUDGET_USD_PER_1K_CACHE_READ` | Cache read $/1k |
| `NSA_BUDGET_USD_PER_1K_CACHE_WRITE` | Cache write $/1k |
| `NSA_BUDGET_KV_USD_PER_GB_S` | KV residency |

## Plugins

Register alternate `ICostModel` implementations via `budget.plugins` for cloud API spill, committed-use effective rates, or self-host amortization.
