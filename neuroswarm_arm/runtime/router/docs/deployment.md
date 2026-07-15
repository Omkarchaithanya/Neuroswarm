# Deployment (GCP Axion)

1. Install deps (`uv sync --all-groups`) — includes `turbovec`, `onnxruntime`, `sentence-transformers`.
2. Set `NSA_TOOL_METADATA_ROOT=templates/mcp-servers`.
3. Optional: Redis for shared embedding cache.
4. Expose `/tools/route` and `/router/health` via gateway.
5. Capture evidence: `POST /tools/route` + `POST /router/benchmark`.

Helm: keep BGE as CPU sidecar or in-process (default in-process for single-VM MVP).
