# MCP templates verification (Axion evidence)

Date: 2026-07-18

## Templates on disk (`templates/mcp-servers/`)

| Template | okf-metadata.yaml | server.py |
|---|---|---|
| web-search | yes | yes |
| github | yes | yes |
| slack | yes | yes |
| browser | yes | yes |
| postgres | yes | yes |
| s3 | yes | yes |

**Count: 6/6** present.

## Runtime router evidence

From `docs/evidence/latest/run_all.json` router cases:

- `tools_indexed`: **6**
- Picked sets include: web-search, github, browser, slack, postgres, s3

From `docs/evidence/latest/tools-route.json` (top-k=3 sample query):

- Returned top-3: web-search, github, slack
- `candidate_count`: **6** (all templates in ANN candidate pool)
- `token_reduction_ratio`: **0.47** on that sample

Honest claim: all 6 templates are indexed and routable; top-k responses surface 3 schemas by design (semantic reduction), not because only 3 exist.

Each `server.py` is a real FastMCP server (real HTTP/SDK clients), not a `tool_payload` stub. Router still indexes via `okf-metadata.yaml` only.
