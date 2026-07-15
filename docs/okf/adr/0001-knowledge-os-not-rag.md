# ADR-0001: NEXUS Knowledge OS over Google OKF (not RAG)

## Status

Accepted

## Decision

Google OKF v0.1 is the portable source format. NEXUS compiles Markdown+YAML into deterministic runtime artifacts for progressive, budgeted retrieval. OKF itself remains a format, not a runtime.

## Consequences

Semantic ANN remains optional and owned by the MCP router for tools. Official §9 validate is separate from NEXUS extension validate.
