# Developer guide

## Package layout

`neuroswarm_arm/runtime/router/` mirrors MAKS/HAOE factory patterns.

## Add a vector backend

1. Implement `VectorIndex` methods in `backends/`.
2. Register in `backends/registry.py` `build_vector_index`.
3. Set `NSA_ROUTER_ANN_BACKEND`.

## Add ranking signal

1. Extend `ranking_features.extract_features`.
2. Add weight on `RerankWeights`.
3. Optional: feed Mem0 via `HistoryRanker`.

## Compat

`neuroswarm_arm.tools.semantic_mcp_router.SemanticMCPRouter` wraps the runtime router for older call sites.
