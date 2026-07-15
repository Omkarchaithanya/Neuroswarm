# ADR 0004: No Circular Dependencies with HAOE

## Status

Accepted

## Context

HAOE, DIPA, KV, Governor, and Gateway must compose.

## Decision

HAOE depends on an injected `handle(req, tool_names)` protocol. DIPA must not import HAOE concretes. Gateway wires both.

## Consequences

- `build_chat_handlers(..., inference=dipa)` 
- Tests can run DIPA without HAOE and vice versa
