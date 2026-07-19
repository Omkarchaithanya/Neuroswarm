# Risk Register — What Could Go Wrong

> Updated for Axion-true MVP. Read before each weekly gate.

---

## P0 risks (live today if ignored)

### R0: Docs claim Graviton5 2-NUMA / CXL; demo is Axion 1-NUMA

**Probability:** Certain if docs unfixed  
**Impact:** Credibility kill with Arm evangelists  

**Mitigation (chosen):** **Option A** — auto-detect topology; degrade on Axion; activate NUMA/CXL on multi-socket. Pitch docs rewritten. No Option B rental required.

### R0b: Stock llama.cpp image while claiming KleidiAI

**Probability:** High (prior evidence showed stock)  
**Impact:** Tech-40 failure  

**Mitigation:** `scripts/deploy-kleidiai-tiers.sh`; `.env` `NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server`; capture gate fails if stock present.

### R0c: Empty metrics / skipped `run_all` (Risk R9 live)

**Mitigation:** `capture-evidence.sh` uses `uv run`, warms chat before `/metrics`, rejects empty scrape, publishes to `docs/evidence/latest/`.

### R0d: Zero Performix evidence despite rules naming it

**Mitigation:** `performix_capture.sh` + GA recipe aliases; Instruction Mix required messaging.

---

## High-priority

### R1: Multi-NUMA host unavailable (was “Graviton5 unavailable”)

**Mitigation:** Axion is primary. Multi-NUMA is optional scale-up. Do not block submit on m9g.

### R2: Performix needs Arm Developer account

**Mitigation:** Sign up Day 1; ship captured JSON under `docs/evidence/performix/`.

### R3: Cascade accept rate soft

**Mitigation:** Tune K; document measured rate honestly.

### R5: CXL unavailable on Axion

**Mitigation:** Pivot C — CXL/MTE as forward-compatible footnote; NVMe/mmap on Axion. Extend same honesty to NUMA-split.

### R6: Arm MCP / apx friction

**Mitigation:** Product path = host `apx` + performix-bridge. Image = `armlimited/arm-mcp:latest`. CLI fallback always.

### R9: Judges cannot reproduce benches

**Mitigation:** `uv sync` + capture script must not write `"skipped"`. Cold `docs/setup.md`.

---

## Medium

### R7: Demo video glitch → record twice; keep B-roll of Compose ps + Performix  
### R8: Helm only linted → real `helm install` timed on GKE/k3s  
### R10: Public repo exposes GCP project/IP → scrub `docs/next-steps-axion.md`  
### R11: SGLang `:latest` missing Arm CPU bits → verify arm64 / pin tag; cite Arm May 2026 blog  

---

## Pivot summary

| If blocked | Pivot |
|---|---|
| No multi-NUMA | Option A (default) |
| No CXL | Footnote + NVMe |
| No Performix auth | Ship prior captures + CLI install docs |
| Kleidi build fails | Document blocker; do **not** claim Kleidi while running stock |

---

## Pre-submit checklist

- [ ] Option A wording everywhere (00–06, Devpost)
- [ ] 3 judges only
- [ ] $2k runner-up noted
- [ ] KleidiAI in `docker compose ps`
- [ ] Performix Instruction Mix present
- [ ] Metrics non-empty
- [ ] `run_all` not skipped
- [ ] GCP IP scrubbed
- [ ] Submit **Aug 13**
