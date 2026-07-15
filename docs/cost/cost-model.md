# RCIS Cost Model

## Formula

\[
C = C_{prompt}+C_{comp}+C_{reason}+C_{cpu}+C_{mem}+C_{energy}+C_{kv}+C_{tool}+C_{retry}+C_{stream}+C_{planner}+C_{queue}+C_{spec}
\]

Each term = configurable rate × observed quantity.

## Env rates (`NSA_RCIS_*`)

| Env | Meaning |
|-----|---------|
| `NSA_RCIS_USD_PER_1K_PROMPT` | Prompt $/1k |
| `NSA_RCIS_USD_PER_1K_COMPLETION` | Completion $/1k |
| `NSA_RCIS_USD_PER_1K_REASONING` | Reasoning $/1k |
| `NSA_RCIS_USD_PER_CPU_SECOND` | CPU amortization |
| `NSA_RCIS_USD_PER_GB_MEMORY_SECOND` | Memory·time |
| `NSA_RCIS_USD_PER_JOULE` | Energy signal |
| `NSA_RCIS_KV_USD_PER_GB_S` | KV residency opportunity |
| `NSA_RCIS_TOOL_CALL_USD` | Tool call |
| `NSA_RCIS_RETRY_USD` | Retry |
| `NSA_RCIS_STREAMING_USD_PER_SECOND` | Streaming |
| `NSA_RCIS_PLANNER_USD_PER_MS` | Planner overhead |
| `NSA_RCIS_QUEUE_USD_PER_MS` | Queue wait |

## Speculation net

`draft + verify − saved_decode` — may be negative (savings).

## Energy

Prefer measured joules / Performix / ArmPMU. Fallback: `psutil` CPU% × (`base_watts + threads × watts_per_thread`).

## Not billing

`estimated_dollars` is a routing objective signal for ARM-native self-host, not an invoice line.
