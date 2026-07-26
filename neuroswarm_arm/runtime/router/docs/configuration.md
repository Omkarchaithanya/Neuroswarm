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
| `NSA_ROUTER_TURBOVEC_BITS` | 4 | TurboVec bit width (**2 or 4** TurboQuant; not int8) |
| `NSA_ROUTER_TURBOVEC_MIN_TOOLS` | 0 | Use TurboVec at/above this catalog size when the wheel imports; else exact NumPy |
| `NSA_ROUTER_METRIC` | `cosine` | cosine\|ip\|l2 |
| `NSA_ROUTER_CACHE` | `memory` | memory\|redis\|disk\|all |
| `NSA_ROUTER_REDIS_URL` | `redis://localhost:6379/1` | Redis cache |
| `NSA_ROUTER_ONNX` | 0 | Enable ONNX path (requires tokenizer) |
| `NSA_ROUTER_ONNX_PATH` | | Path to ONNX embedding model |
| `NSA_ROUTER_TOKENIZER_PATH` | | HF id/path for ONNX tokenizer (else encoder name) |
| `NSA_ROUTER_INT8` | 0 | Prefer INT8 ONNX |
| `NSA_ROUTER_ALLOW_HASH` | 0 | Allow deterministic hash embedder (tests/dev only) |
| `NSA_ROUTER_BGE_QUERY_PREFIX` | 1 | Apply BGE retrieval instruction to **queries only** (`Represent this sentence…`); set 0 to disable |
| `NSA_MCP_EXECUTE` | 0 | Enable `POST /tools/call` via `McpServerManager` (stdio pool + optional HTTP) |
| `NSA_MCP_APPROVE_DESTRUCTIVE` | 0 | Allow destructive tools without per-request `approve=true` |
| `NSA_MCP_BROWSER_HOST_ALLOWLIST` | | Comma hosts; when set, browser/fetch deny-by-default outside list |
| `NSA_MCP_RESULT_MAX_BYTES` | 524288 | Cap MCP tools/call result JSON size |
| `NSA_MCP_MAX_INFLIGHT` | 2 | Max concurrent RPCs per MCP server session |
| `NSA_MCP_HTTP_<SERVER>` | | Streamable HTTP MCP URL for remote server id |
| `DATABASE_URL_READONLY` | | Preferred DSN for postgres query/list/describe/explain |
| `NSA_ROUTER_HOT_RELOAD` | 1 | OKF filesystem watch |
| `NSA_ROUTER_AFFINITY_CORES` | | Comma CPU list |
| `NSA_ROUTER_OTEL` | 0 | Enable OTEL spans |

Hybrid weight defaults (`HybridWeights`, sum = 1.0):

| `w_semantic` | `w_keyword` | `w_param` | `w_capability` | `w_workflow` | `w_agent` | `w_popularity` | `w_history` | `w_latency_cost` |
|--------------|-------------|-----------|----------------|--------------|-----------|----------------|-------------|------------------|
| 0.40 | 0.12 | 0.10 | 0.08 | 0.08 | 0.06 | 0.04 | 0.06 | 0.06 |

Env overrides: `NSA_ROUTER_W_SEMANTIC`, `_KEYWORD`, `_PARAM`, `_CAPABILITY`, `_WORKFLOW`, `_AGENT`, `_POPULARITY`, `_HISTORY`, `_LATENCY_COST`.

## Notes

- Production default is **FastEmbed** (`BAAI/bge-small-en-v1.5`). Without FastEmbed / Sentence-Transformers / ONNX, startup raises unless `NSA_ROUTER_ALLOW_HASH=1`.
- Query embeds use the BGE instruction prefix by default (`NSA_ROUTER_BGE_QUERY_PREFIX=1`); tool/document embeds stay unprefixed. Restoring the prefix can raise cosine bands — **do not retune 0.42/0.70** until a FastEmbed measurement artifact exists.
- Pooling is FastEmbed library-default (not configured in-repo); do not claim mean vs CLS from this codebase alone.
- ONNX never silently hash-encodes: missing tokenizer raises `EmbeddingError`.
- Health reports `degraded` when configured `turbovec` fails to import. Below `NSA_ROUTER_TURBOVEC_MIN_TOOLS`, exact numpy is intentional (`status=ok`). Ready payload includes honest `configured_backend` / `active_backend` / `fallback_reason` / `catalog_size` (never treat `ann_backend=turbovec+exact` as proof TurboVec handled the query).
- Measured `RoutingResult.token_reduction_ratio` (e.g. `reduction≈0.89`) is a **schema-token estimate** (`1 - tokens_after/tokens_before`), not a literal 40→3 tool-count cut (~92%). Cite the token ratio from live FastEmbed artifacts; treat 40→3/92% as aspirational count cut only.
- High-conf → `thinking_token_cap=256` applies when router `high_confidence` is consulted (tool/execute path). Ordinary L3 chat turns use the RTG default cap (~1046) and do not force the high-conf budget.
- TurboVec is an optional experimental ARM64 ANN backend using **2-bit or 4-bit TurboQuant** compression — not an int8 index. `router_turbovec_search_ms` is updated only when TurboVec is active; use `router_search_latency_ms` for any-backend search latency.
- Custom SVE2 codebook kernels are out of scope; `sve_kernels_active` stays false.
- `POST /tools/call` is optional execute via **`McpServerManager`** (warm stdio sessions + optional Streamable HTTP). Protocol negotiated as `2025-11-25`. YAML schemas are still used for routing embeddings; tools become **`executable`** only after live `tools/list` reconcile. Destructive tools require `approve=true` or `NSA_MCP_APPROVE_DESTRUCTIVE=1`. Child processes get per-server env allowlists (not full parent `os.environ`). Advertised `*.tool.yaml` IDs must match FastMCP names (`scripts/verify-mcp-execute-contract.py`); with `NSA_MCP_EXECUTE=1` the script can optionally require a live `tools/list`.
- Security controls in templates: browser/web-search SSRF (`mcp_ssrf`), postgres read-only SQL gate + `DATABASE_URL_READONLY`, S3 no-overwrite default + `IfNoneMatch`.
- OTel (when `NSA_ROUTER_OTEL=1`): spans emit both `gen_ai.system` and `gen_ai.provider.name`, plus MCP execute attrs `mcp.method.name` / `mcp.session.id` / `mcp.protocol.version`.
