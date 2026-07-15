# Risk Register — What Could Go Wrong

> Mitigation plan for every realistic failure mode. Read this before Week 1.

---

## High-priority risks

### R1: Graviton5 (m9g) not available in your AWS region

**Probability:** Medium (m9g GA'd June 2026, may not be in all regions yet)
**Impact:** High (the headline hardware claim)

**Mitigation:**
- Use Graviton4 (c8g.4xlarge) as fallback — code paths work identically
- Document both targets in setup.md: "Tested on m9g (preferred) and c8g (fallback)"
- The KleidiAI + I8MM + SVE2 path is the same on V2 and V3 cores
- Add a sentence to README: "Future-compat verified on Arm AGI CPU dev-kit (when sampling)"

### R2: Arm Performix CLI download requires Arm Developer account

**Probability:** High (it does require account)
**Impact:** Low (free signup)

**Mitigation:**
- Sign up for Arm Developer account on Day 1 — takes 5 minutes
- Document the signup flow in `docs/setup.md`
- Provide pre-captured benchmark JSON files in `benchmarks/` so reviewers can see results without running Performix themselves

### R3: Cascade acceptance rate below 70%

**Probability:** Medium (depends heavily on prompt distribution)
**Impact:** Medium (weaker speedup claim)

**Mitigation:**
- Tune draft length K (try K=4, 5, 6, 8)
- Switch to self-speculation (`--spec-self ngram-map-k`) for repetitive prompts
- Use a slightly larger drafter (1.5B) if 0.5B underperforms
- Add a fallback message: "Cascade is heuristic; self-spec gives guaranteed gains"

### R4: Mem0 self-hosting setup takes too long

**Probability:** Low (Mem0 is fast to spin up)
**Impact:** Low (we can stub it)

**Mitigation:**
- Use Mem0 cloud (free tier) for the demo
- Self-host only if time permits
- Stub fallback: plain FAISS namespace with Mem0-compatible API

### R5: CXL emulation over RDMA adds unexpected latency

**Probability:** High (we know it'll be ~6 µs, but real number may vary)
**Impact:** Low (we measure it, document it)

**Mitigation:**
- Measure early in Week 3
- If >50 µs, swap to NVMe-only pager for demo, document the CXL path as production-only
- Always document: "On Arm AGI CPU dev-kit, native CXL 3.0 gives sub-µs; on Graviton5, software emulation gives X µs"

### R6: Arm MCP server has integration bugs

**Probability:** Medium (it's brand new, May 2026)
**Impact:** Low (we use Performix CLI as fallback)

**Mitigation:**
- Run Performix CLI manually as fallback
- Wrap MCP calls in try/except
- Document both code paths

---

## Medium-priority risks

### R7: Demo video hits a glitch during recording

**Probability:** High (demo videos always do)
**Impact:** Medium

**Mitigation:**
- Script it tightly — every second counted
- Record multiple takes, edit together
- Have a backup terminal recording just in case
- 3-minute hard cap, no exceptions

### R8: Submissions get cut off due to Devpost issues on Aug 14

**Probability:** Medium (Devpost has had issues in past hackathons)
**Impact:** High (we miss the deadline)

**Mitigation:**
- **Submit Aug 13**, not Aug 14 — non-negotiable
- Test the submission form field-by-field on Aug 12
- Keep all files in a `submission/` folder ready to copy-paste

### R9: Judges can't reproduce our benchmark

**Probability:** Medium
**Impact:** High (low tech score)

**Mitigation:**
- Provide `benchmarks/run-all.sh` that reproduces every number
- Pre-capture all Performix outputs in `benchmarks/`
- Include the exact test prompts in `benchmarks/test-data/`
- Provide `docs/reproduce-benchmarks.md` with a single command

### R10: helm install fails on fresh clone

**Probability:** Medium (K8s dependencies, RBAC, ingress)
**Impact:** High (UX score)

**Mitigation:**
- Test on a brand-new cluster before submitting
- Provide a `docker-compose.yaml` alternative for single-node deploy
- Both paths must work in <90 seconds

---

## Low-priority risks

### R11: Some required tool (e.g., ExecuTorch) has Arm64 compatibility issues

**Probability:** Low
**Impact:** Low

**Mitigation:**
- ExecuTorch is listed as "optional fallback" in our architecture — not on critical path
- Mention it but don't gate the demo on it

### R12: README too long, judges skim and miss the wow

**Probability:** Medium
**Impact:** Medium

**Mitigation:**
- README frontmatter is 1 screen of scroll
- Architecture diagram above the fold
- Benchmark table immediately visible
- Link out to details, don't put everything in README

### R13: A judge has a different definition of "agentic"

**Probability:** Low
**Impact:** Low

**Mitigation:**
- Track explicitly says "agentic workloads that combine multiple AI models, MCP servers, and integrations" — we hit all three (cascade models + MCP servers + LangGraph integration)

---

## Risk priority matrix

| Risk | Probability | Impact | Priority |
|---|---|---|---|
| R8 — Deadline miss | Medium | High | **P0** |
| R1 — Graviton5 unavailable | Medium | High | **P0** |
| R9 — Benchmarks not reproducible | Medium | High | **P0** |
| R10 — helm install broken | Medium | High | **P0** |
| R3 — Cascade acceptance low | Medium | Medium | P1 |
| R7 — Demo video glitches | High | Medium | P1 |
| R5 — CXL emulation slow | High | Low | P1 |
| R2 — Performix account | High | Low | P2 |
| R6 — MCP server bugs | Medium | Low | P2 |
| R4 — Mem0 setup | Low | Low | P3 |
| R11 — ExecuTorch issues | Low | Low | P3 |
| R12 — README too long | Medium | Medium | P1 |
| R13 — Judge definition | Low | Low | P3 |

**P0 risks must be mitigated by Day 7 (end of Week 1).**

---

## If we need to pivot mid-build

**Pivot A: Cascade doesn't hit speedup target**
- Fall back to: llama.cpp self-speculation alone (2-5× already proven in community)
- Pitch shifts: "Self-speculative decoding on Graviton5" — simpler story, still wow

**Pivot B: Performix unavailable**
- Use `perf` + `bpftrace` directly + flamegraph.pl
- Generate the same flame graphs manually
- Wrap in a Python script so it's still "tool-driven"

**Pivot C: CXL feature doesn't work at all**
- Remove it from the headline pitch
- Keep NVMe pager as the "KV survival" story
- Document CXL as a "future path" footnote

**Pivot D: Behind schedule in Week 4**
- Cut to: cascade + Performix + Helm + 2 MCP templates
- Still shipable. Still wins on tech + impact.

**Pivot E: Can't get demo video done**
- Substitute: animated architecture diagram + terminal screencast
- Judges care about the project, not the video production quality

---

## What success looks like

**Best case:** Aug 14 — submit fully working NeuroSwarm-Arm with all 7 layers, demo video, Helm chart, 6 MCP templates. Sep 15 — winner announcement.

**Acceptable case:** Aug 14 — submit cascade + Performix + semantic router + governor + dashboard + 2 MCP templates. Strong tech + impact, weaker on polish.

**Failure case:** Aug 14 — last-minute submit with broken helm install, video >5 min, claims that don't reproduce.

**The difference:** the failure case is what happens when you don't read this document.

---

## Open questions to answer in Week 1

- [ ] Which AWS region has m9g.4xlarge available?
- [ ] What's the real cascade acceptance rate on representative agent prompts?
- [ ] Does Arm Performix CLI run cleanly via the MCP server?
- [ ] What's the actual Mem0 cloud vs. self-host latency?
- [ ] What's the real CXL emulation latency (RDMA vs. NVMe fallback)?
- [ ] Does the Arm MCP server have the tools we expect?

Answer all 6 by end of Week 1 before committing to architecture.