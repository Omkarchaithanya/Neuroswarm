# Data flow

1. OKF / YAML / JSON / Markdown loaders populate `ToolRegistry`.
2. `IncrementalIndexer` embeds `ToolRecord.index_text()` and upserts TurboVec.
3. Query embedding hits multi-tier cache (memory → Redis → disk).
4. ANN returns candidate_k = top_k * multiplier.
5. Hybrid fusion blends semantic/keyword/param/capability/workflow/agent/history/cost.
6. Filters enforce security / workflow / agent constraints.
7. Reranker applies weighted LTR features (+ optional RL hook).
8. Serializer builds MCP function schemas; DIPA injects only those.
9. Metrics record latency breakdown and token reduction.
