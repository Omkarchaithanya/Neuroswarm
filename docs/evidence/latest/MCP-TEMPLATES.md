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
- Top-K=3 → token reduction vs naïve-all **≥0.85** on the 40-tool fixture
- High-conf gate 0.85 → `thinking_token_cap=256` when top-1 confidence clears

Each `server.py` remains a real FastMCP server. Optional execute: `NSA_MCP_EXECUTE=1` + `POST /tools/call`. Chat path still injects schemas only (not an MCP proxy).
