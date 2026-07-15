# Architecture

## Class diagram

```mermaid
classDiagram
  class SemanticToolRouter {
    +register_tool()
    +route()
    +batch_route()
    +reload()
    +snapshot()
    +restore()
  }
  class ToolRegistry
  class EmbeddingService
  class VectorIndex
  class TurboVecIndex
  class HybridSearch
  class Reranker
  class HistoryRanker
  SemanticToolRouter --> ToolRegistry
  SemanticToolRouter --> EmbeddingService
  SemanticToolRouter --> VectorIndex
  SemanticToolRouter --> HybridSearch
  SemanticToolRouter --> Reranker
  SemanticToolRouter --> HistoryRanker
  TurboVecIndex ..|> VectorIndex
```

## Design rules

- Router owns tool selection; DIPA never indexes tools.
- Only top-K MCP schemas enter the LLM prompt.
- TurboVec is default ANN; exact numpy is Axion-safe fallback.
- Mem0 / OKF / ARMORA / AQR signals feed reranking, not hard gates (except security deny policies).
