# ADR-0004: HardwareTopology HAL

## Status

Accepted

## Decision

Never hardcode NUMA node counts. Discover via `HardwareTopology`; if unavailable, allocate locally. CXL remains a future hint flag.

## Consequences

Portable to single-node Axion VMs and multi-NUMA Neoverse hosts.
