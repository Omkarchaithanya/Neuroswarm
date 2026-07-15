# ADR-0001: ACR is a Context Operating System, not RAG

## Status

Accepted

## Decision

Adaptive Context Runtime plans and compresses context. OKF remains hierarchy/graph knowledge; Mem0 remains episodic memory. Semantic ANN is not the core of ACR.

## Consequences

No generic RAG framework in `runtime/acr`. Optional embeddings stay inside memory provider boundary.
