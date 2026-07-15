# OKF + NEXUS Knowledge OS

Google **Open Knowledge Format (OKF)** is the portable Markdown+YAML **format**.

NEXUS **Knowledge OS** is the optional compiler/runtime **over** OKF.

They are not the same thing.

## Separation

- Mem0: user/agent episodic facts
- OKF: institutional Markdown+YAML knowledge (Google format)
- NEXUS compiler/runtime: indexes, ranking, budgets, progressive retrieval

## Chat DAG

```
mem0_recall → okf_context → semantic_route → okf_tool_docs → kv_session → cascade → …
```

## CLI

```bash
uv sync --all-groups
uv run okf validate --layer official
uv run okf validate --layer both
uv run okf build --source okf --strict
uv run okf query "cascade policy" --agent architect
```

## Env

- `NSA_OKF_ROOT` (default `okf`)
- `NSA_OKF_ARTIFACTS` (default `okf/.okf/artifacts`)
- `NSA_OKF_ENABLED`
- `NSA_OKF_TOKEN_BUDGET`

## Docs

- [SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md)
- [GAP_ANALYSIS.md](GAP_ANALYSIS.md)
- ADRs in `adr/`
