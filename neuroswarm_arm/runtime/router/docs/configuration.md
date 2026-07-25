# Configuration

| Env | Default | Meaning |
|-----|---------|---------|
| `NSA_ROUTER_TOP_K` | 3 | Tools returned |
| `NSA_ROUTER_THRESHOLD` | 0.42 | Semantic expand / re-rank trigger |
| `NSA_ROUTER_RERANK_TRIGGER` | (alias of threshold) | Same expand gate as `NSA_ROUTER_THRESHOLD` |
| `NSA_ROUTER_HIGH_CONF_GATE` | 0.70 | `RoutingResult.high_confidence` when top-1 confidence exceeds this (FastEmbed-calibrated; was 0.85 for hash peaks) |
| `NSA_ROUTER_HIGH_CONF_THINKING_BUDGET` | 256 | Cap `thinking_token_cap` when high-confidence |
| `NSA_ROUTER_ENCODER` | `BAAI/bge-small-en-v1.5` | Embedding model (**384-dim**, ~33.4M params) |
| `NSA_ROUTER_EMBEDDING_BACKEND` | `fastembed` | fastembed\|sentence-transformers\|onnx\|hash |
| `NSA_ROUTER_FASTEMBED_CACHE` | | FastEmbed model cache dir (also `FASTEMBED_CACHE_PATH`) |
| `NSA_ROUTER_ANN_BACKEND` | `turbovec` | turbovec\|exact\|faiss\|hnsw\|usearch\|scann |
| `NSA_ROUTER_TURBOVEC_BITS` | 4 | TurboVec bit width (**2 or 4**) |
| `NSA_ROUTER_TURBOVEC_MIN_TOOLS` | 100 | Use TurboVec only at/above this catalog size; else exact |
| `NSA_ROUTER_METRIC` | `cosine` | cosine\|ip\|l2 |
| `NSA_ROUTER_CACHE` | `memory` | memory\|redis\|disk\|all |
| `NSA_ROUTER_REDIS_URL` | `redis://localhost:6379/1` | Redis cache |
| `NSA_ROUTER_ONNX` | 0 | Enable ONNX path (requires tokenizer) |
| `NSA_ROUTER_ONNX_PATH` | | Path to ONNX embedding model |
| `NSA_ROUTER_TOKENIZER_PATH` | | HF id/path for ONNX tokenizer (else encoder name) |
| `NSA_ROUTER_INT8` | 0 | Prefer INT8 ONNX |
| `NSA_ROUTER_ALLOW_HASH` | 0 | Allow deterministic hash embedder (tests/dev only) |
| `NSA_MCP_EXECUTE` | 0 | Enable `POST /tools/call` against template FastMCP servers |
| `NSA_ROUTER_HOT_RELOAD` | 1 | OKF filesystem watch |
| `NSA_ROUTER_AFFINITY_CORES` | | Comma CPU list |
| `NSA_ROUTER_OTEL` | 0 | Enable OTEL spans |

Hybrid weights: `NSA_ROUTER_W_SEMANTIC`, `_KEYWORD`, `_PARAM`, `_CAPABILITY`, `_WORKFLOW`, `_AGENT`, `_POPULARITY`, `_HISTORY`, `_LATENCY_COST`.

## Notes

- Production default is **FastEmbed** (`BAAI/bge-small-en-v1.5`). Without FastEmbed / Sentence-Transformers / ONNX, startup raises unless `NSA_ROUTER_ALLOW_HASH=1`.
- ONNX never silently hash-encodes: missing tokenizer raises `EmbeddingError`.
- Health reports `degraded` when configured `turbovec` fails to import. Below `NSA_ROUTER_TURBOVEC_MIN_TOOLS`, exact numpy is intentional (`status=ok`).
- Custom SVE2 codebook kernels are out of scope; `sve_kernels_active` stays false.
- `POST /tools/call` is optional demo execute only — the router remains a schema selector for chat.
