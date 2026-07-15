# ADR 0003: Work Stealing with Locality Preference

## Status

Accepted

## Context

Production runtimes (Cilk, TBB, Tokio, Ray) use work stealing to keep cores busy without a global lock. Agent workloads also care about memory/CPU locality for KV and cascade tiers.

## Decision

Each worker owns a private deque (owner LIFO left; thief FIFO right / oldest). A per-pool overflow queue holds unbound work. Steal prefers matching `locality_tag` when present, otherwise accepts any eligible task. No global scheduler lock — only per-queue locks.

## Consequences

- Good utilization under imbalance
- Chat path still uses deterministic DAG execution for latency SLOs
- Steal metrics exported as `haoe_steal_total`
