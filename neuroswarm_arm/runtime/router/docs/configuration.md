# Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `NSA_ROUTER_TOP_K` | 3 | Tools returned |
| `NSA_ROUTER_THRESHOLD` | 0.42 | Semantic expand threshold |
| `NSA_ROUTER_ENCODER` | `BAAI/bge-small-en-v1.5` | Embedding model |
| `NSA_ROUTER_ANN_BACKEND` | `turbovec` | turbovec\|exact\|faiss\|hnsw\|usearch\|scann |
| `NSA_ROUTER_METRIC` | `cosine` | cosine\|ip\|l2 |
| `NSA_ROUTER_CACHE` | `memory` | memory\|redis\|disk\|all |
| `NSA_ROUTER_REDIS_URL` | `redis://localhost:6379/1` | Redis cache |
| `NSA_ROUTER_ONNX` | 0 | Enable ONNX path |
| `NSA_ROUTER_INT8` | 0 | Prefer INT8 ONNX |
| `NSA_ROUTER_HOT_RELOAD` | 1 | OKF filesystem watch |
| `NSA_ROUTER_AFFINITY_CORES` | | Comma CPU list |
| `NSA_ROUTER_OTEL` | 0 | Enable OTEL spans |

Hybrid weights: `NSA_ROUTER_W_SEMANTIC`, `_KEYWORD`, `_PARAM`, `_CAPABILITY`, `_WORKFLOW`, `_AGENT`, `_POPULARITY`, `_HISTORY`, `_LATENCY_COST`.
