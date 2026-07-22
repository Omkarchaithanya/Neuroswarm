# Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `NSA_ROUTER_TOP_K` | 3 | Tools returned |
| `NSA_ROUTER_THRESHOLD` | 0.42 | Semantic expand / re-rank trigger |
| `NSA_ROUTER_RERANK_TRIGGER` | (alias of threshold) | Same expand gate as `NSA_ROUTER_THRESHOLD` |
| `NSA_ROUTER_HIGH_CONF_GATE` | 0.85 | `RoutingResult.high_confidence` when top-1 confidence exceeds this |
| `NSA_ROUTER_HIGH_CONF_THINKING_BUDGET` | 256 | Cap `thinking_token_cap` when high-confidence |
| `NSA_ROUTER_ENCODER` | `BAAI/bge-small-en-v1.5` | Embedding model (**384-dim**, ~33.4M params) |
| `NSA_ROUTER_ANN_BACKEND` | `turbovec` | turbovec\|exact\|faiss\|hnsw\|usearch\|scann |
| `NSA_ROUTER_TURBOVEC_BITS` | 4 | TurboVec bit width (**2 or 4**) |
| `NSA_ROUTER_METRIC` | `cosine` | cosine\|ip\|l2 |
| `NSA_ROUTER_CACHE` | `memory` | memory\|redis\|disk\|all |
| `NSA_ROUTER_REDIS_URL` | `redis://localhost:6379/1` | Redis cache |
| `NSA_ROUTER_ONNX` | 0 | Enable ONNX path (requires tokenizer) |
| `NSA_ROUTER_ONNX_PATH` | | Path to ONNX embedding model |
| `NSA_ROUTER_TOKENIZER_PATH` | | HF id/path for ONNX tokenizer (else encoder name) |
| `NSA_ROUTER_INT8` | 0 | Prefer INT8 ONNX |
| `NSA_ROUTER_ALLOW_HASH` | 0 | Allow deterministic hash embedder (tests/dev only) |
| `NSA_ROUTER_HOT_RELOAD` | 1 | OKF filesystem watch |
| `NSA_ROUTER_AFFINITY_CORES` | | Comma CPU list |
| `NSA_ROUTER_OTEL` | 0 | Enable OTEL spans |

Hybrid weights: `NSA_ROUTER_W_SEMANTIC`, `_KEYWORD`, `_PARAM`, `_CAPABILITY`, `_WORKFLOW`, `_AGENT`, `_POPULARITY`, `_HISTORY`, `_LATENCY_COST`.

## Notes

- Without a real Sentence-Transformers / ONNX backend, startup raises unless `NSA_ROUTER_ALLOW_HASH=1`.
- ONNX never silently hash-encodes: missing tokenizer raises `EmbeddingError`.
- Health reports `degraded` when configured `turbovec` falls back to numpy.
