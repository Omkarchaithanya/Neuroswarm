# NEXUS Memory Module → Official Mem0 Mapping

| NEXUS module | Official Mem0 feature | Extension reason |
|--------------|----------------------|------------------|
| `adapter/Mem0Adapter` | `Memory.add` / `search` / `get` / `delete` / `get_all` | Thin wrap; sole SDK boundary |
| `adapter/sdk_client.py` | `Memory.from_config` | Config: Qdrant path, LLM, embedder |
| Typed `remember_fact/tool/...` | `add` + `metadata.memory_type` | NEXUS typed memory taxonomy |
| Namespaces (`tools/`, `reflection/`, …) | `metadata.namespace` + `user_id`/`agent_id`/`run_id` | Multi-tenant NEXUS scopes |
| `search` / `retrieve` | Hybrid `Memory.search(filters=...)` | Do not reimplement semantic/BM25/entity |
| `update` | ADD-only new fact + `metadata.supersedes_id` | v3 forbids in-place UPDATE extraction |
| `delete` / `forget` | `Memory.delete` | Retention/TTL only |
| `ranking/` | Post-Mem0 importance/TTL re-rank | Metadata policy after official score |
| `compression/` / ACR compression | N/A (app layer) | Context size after retrieval |
| `reflection/` | `add` of reflection facts | Layer 5 reflects; Mem0 stores |
| `prediction/` | Reads prior Mem0 hits | Speculative prefetch hints |
| `retention/` / TTL policies | `delete` + metadata | App retention on top of ADD-only store |
| `summarization/` | App summary before/after retrieve | Not Mem0 extraction |
| `providers/json_fallback` | Emergency only | Circuit breaker when Mem0 init fails |
| OKF | Not Mem0 | Static institutional knowledge |
| KV / MAKS | Not Mem0 | Inference token pages |
| Custom `graph.py` | **Deprecated** | Use Mem0 entity linking |

## Official workflow mapping

| Step | Official | NEXUS |
|------|----------|-------|
| Interaction | messages | HAOE chat / ACR plan |
| Extraction | `Memory.add(messages)` | `Mem0Adapter.remember(messages=...)` |
| Storage | vector + entity store | Qdrant via Mem0 config |
| Retrieval | `Memory.search` | `Mem0Adapter.search` |
| Ranking | Mem0 hybrid score | + optional importance boost |
| Compression | — | ACR / compression/ after retrieve |
| Prompt | inject memories | merge_mem0_okf / ACR assembly |
