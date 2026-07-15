# ADR 0001: Runtime Kernel, Not a Scheduler

## Status

Accepted

## Context

NEXUS-ARM docs describe HAOE as a “scheduler,” but the platform requires agent lifecycle, task graphs, resource allocation, affinity, telemetry, and workflow semantics. Treating HAOE as only a queue would push orchestration into the gateway and recreate GIL-bound spaghetti.

## Decision

HAOE is the **agent runtime kernel** (Layer 1). Scheduling is one subsystem. Everything in the agent plane executes through HAOE. HAOE never performs inference.

## Consequences

- Gateway submits workflows / callables; it does not own execution policy
- Clear boundary for ARMORA, Swarm, AWPP hooks later
- Slightly larger surface area than a stub scheduler — intentional
