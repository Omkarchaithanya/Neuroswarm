# nexus-okf — NEXUS Knowledge OS over Google OKF

**Google Open Knowledge Format** = format (Markdown + YAML).  
**NEXUS Knowledge OS** = compiler + runtime extensions.

Import package: `nexus_okf` (avoids collision with corpus dir `okf/`).  
CLI: `okf`.

## Layers

1. `nexus_okf.official` — Google SPEC §9 (Concept ID = path, free-form `type`)
2. `nexus_okf.compiler` / `runtime` — NEXUS extensions

## Install

```bash
uv sync --all-groups
# or package only:
uv pip install -e packages/okf
```

## CLI

```bash
okf validate --layer official
okf validate --layer nexus
okf build --source okf --strict
okf query "cost budget" --agent architect
```

Mem0 stores user memories. OKF stores institutional knowledge. Never mix.
