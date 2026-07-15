# ADR 0004: No Circular Dependencies

## Status

Accepted

## Context

Gateway, Cascade, KV, Governor, Evolution, and HAOE must compose. Import cycles break packaging and testing.

## Decision

HAOE depends only on ABCs/protocols and injected callables. Integration adapters (`integration/chat.py`) live inside HAOE but type against protocols. Downstream components may depend on HAOE; HAOE must not import their concrete modules.

## Consequences

- `build_chat_handlers` receives router/cascade/kv as arguments
- KV pressure is a callable/protocol, not `KVRuntimeManager`
- Evolution/Performix consume outbound snapshots only
