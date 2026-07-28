# MCP templates verification (Axion evidence)

Updated: 2026-07-24 (Pillar 2 catalog expansion)

## Templates on disk (`templates/mcp-servers/`)

| Template | `tools/*.tool.yaml` | `server.py` | notes |
|---|---|---|---|
| web-search | yes (5) | yes | schemas for routing |
| github | yes (8) | yes | |
| slack | yes (7) | yes | |
| browser | yes (6) | yes | |
| postgres | yes (7) | yes | |
| s3 | yes (7) | yes | |

**Total tool schemas: ≥40** (per-tool `*.tool.yaml`). Server info moved to `okf-server-info.yaml` (not indexed).

## Runtime router evidence (target after FastEmbed gateway rebuild)

- `tools_registered` / `indexed_count`: **≥40**
- `embedding_backend`: **fastembed** (not hash)
- `embedding_dims`: **384**
- Top-K=3 → schema-**token** reduction vs naïve-all (live Axion FastEmbed often ≈**0.89**; not the same as a 40→3 / 92% tool-count cut)
- High-conf gate **0.70** → `thinking_token_cap=256` when top-1 confidence clears (gated tool path; chat RTG default cap is separate)

Each `server.py` remains a real FastMCP **stdio** server. Optional execute: `NSA_MCP_EXECUTE=1` + `POST /tools/call` via `McpServerManager` (protocol `2025-11-25`, warm pool, env allowlists). Streamable HTTP remotes: `NSA_MCP_HTTP_<SERVER>=url`. Tools are **executable** only after live `tools/list` reconcile (YAML IDs alone are for routing). Chat path still injects schemas (not a full MCP proxy). Release controls: SSRF on browser/fetch, postgres RO SQL gate, S3 no-overwrite default, destructive `approve=true`.
