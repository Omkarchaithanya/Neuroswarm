# Submission hygiene checklist

**Submit target: Aug 13, 2026** (not Aug 14).

## Evidence pack (must be in repo / linked)

- [x] `docs/evidence/latest/` — Kleidi PASS, `run_all` ok, non-empty metrics, chat
- [x] `docs/evidence/performix/` — `01-code_hotspots.json` + `02-instruction_mix.json` + CSV + **`OPTIMIZATIONS.md`** + flame `screenshots/05-code-hotspots-flame.png`
- [x] `05-BENCHMARK-PLAN.md` measured table filled (under-claim OK)
- [x] Option A / Axion-true README + Devpost overview
- [x] SGLang `:latest` arm64 verified
- [x] Judges = 3 only; Runner-Up $2k noted
- [x] GCP project/IP scrubbed from `docs/next-steps-axion.md` (placeholders)

## Before click Submit

1. Paste `docs/DEVPOST-OVERVIEW.md` into Devpost Project Overview
2. Link public GitHub repo
3. Upload demo video (`docs/DEMO-VIDEO-CHECKLIST.md`) — still do it
4. Confirm Compose evidence still shows KleidiAI image (re-run capture if stack drifted)
5. Double-check no “NUMA-split Graviton5 demo” wording anywhere judge-facing

## Red-flag table (final)

| Risk | Status |
|---|---|
| Stock ggml image in evidence | Cleared (KleidiAI) |
| Empty metrics / skipped run_all | Cleared |
| Zero Performix | Cleared (hotspots + instruction_mix + OPTIMIZATIONS.md + flame PNG) |
| Invented recipes | Cleared (GA IDs) |
| 4th judge | Cleared |
| `arm/mcp:latest` | Cleared (`armlimited/arm-mcp`) |
