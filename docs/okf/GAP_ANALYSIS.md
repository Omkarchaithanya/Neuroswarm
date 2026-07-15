# Origin: NEXUS Extension (docs)
# OKF Gap Analysis (Google v0.1 vs NEXUS)

## Categories

### A — Official OKF (implement exactly)

Markdown + YAML, required `type`, reserved index/log, path Concept ID, permissive consumption.

### B — Compatible NEXUS extensions

Compiler, artifacts (`.okf/`), runtime, ranking, budgets, wikilinks, `mount`/`token_budget`/`ontology` FM keys, Mem0/MCP/HAOE integration.

### C — Conflicts remediated

| ID | Issue | Fix applied |
|----|-------|-------------|
| C1 | Type enum | Official schema = free string; NEXUS schema separate |
| C2 | Type auto-default | Removed on official/concept path |
| C3 | Custom id as primary | Official ID = path; FM `id` = NEXUS alias |
| C4 | index.md full FM | Root only `okf_version`; nested indexes body-only |
| C5 | log.md FM | Body-only ISO log |
| C6 | Mixed validators | `--layer official\|nexus\|both` |
| C7 | Framing | Docs: Knowledge OS **over** OKF |
| C8 | Bare MD | `arop.md` and `gepa.md` have FM |
| C9 | migrate invents fields | `migrate --mode official` vs `nexus` |

### D — Outside OKF scope

HAOE, DIPA, ARMORA, Mem0, MCP router, Performix, GEPA, Prometheus — NEXUS subsystems consuming OKF.
