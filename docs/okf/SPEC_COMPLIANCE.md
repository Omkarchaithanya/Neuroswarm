# Origin: NEXUS Extension (docs)
# OKF Spec Compliance Matrix

**Authoritative:** Google Open Knowledge Format v0.1 — vendored at [`packages/okf/nexus_okf/official/SPEC.md`](../../packages/okf/nexus_okf/official/SPEC.md)  
Upstream: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

NEXUS implements **Google OKF as Layer 1** and a **Knowledge OS as Layer 2**. Google SPEC is never rewritten.

## Layer model

| Layer | Package | Role |
|-------|---------|------|
| Official OKF | `nexus_okf.official` | Parse, Concept ID=path, §9 validate |
| NEXUS Extension | `nexus_okf.compiler` / `runtime` / … | Compiler, graph, rank, budget, runtime |

## Compliance matrix (summary)

| Spec § | Requirement | Status |
|--------|-------------|--------|
| §2 Concept ID | path minus `.md` | Done (`official.parse.concept_id`) |
| §3.1 Reserved | `index.md`, `log.md` | Done |
| §4.1 `type` required | non-empty; no auto-default on official path | Done |
| §4.1 free-form types | no enum in official schema | Done |
| §4.1 unknown keys | preserve / do not reject | Done |
| §5 broken links | not errors | Done (official never fails) |
| §6 index.md | no FM except root `okf_version` | Done (corpus + validator) |
| §7 log.md | no FM; ISO dates | Done |
| §9 conformance | official validator only | Done (`okf validate --layer official`) |

## CLI

```bash
okf validate --layer official   # Google §9
okf validate --layer nexus      # NEXUS extensions
okf validate --layer both
okf build --require-official
```
