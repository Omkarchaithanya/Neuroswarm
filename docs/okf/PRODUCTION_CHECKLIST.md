# OKF / NEXUS Knowledge OS — Production Readiness Checklist

## Official OKF (Google §9)

- [x] `nexus_okf.official` parse + Concept ID = path
- [x] Official validator (§9 only)
- [x] Corpus index/log §6/§7 conformant
- [x] Free-form `type` (no official enum)
- [x] `okf validate --layer official` CI gate
- [x] Vendored SPEC.md reference

## NEXUS Layer

- [x] Compiler + artifacts under `.okf/`
- [x] Dual validate official|nexus|both
- [x] Mem0/OKF separation
- [x] MCP post-route tool docs
- [x] HAOE chat DAG integration
- [x] SDK stubs
- [ ] 100k-doc soak on Axion
