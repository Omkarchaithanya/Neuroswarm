# Submission Strategy — Win the Judges' Eyes

> How to write the README, the demo video, and the Devpost form so judges score us max on all four criteria.

---

## Understanding the judges

**4 judges:**
- Avin Zarlez — Arm Staff SW Engineer, Developer Evangelist
- Michael Hall — Arm Principal SW Engineer, Developer Evangelist
- Gabriel Peterson — Arm Senior ML Engineer, Developer Evangelist
- Rani Chowdary Mandepudi — SW Engineer, Strategy & Ecosystems

**What they care about (read between the lines):**
- They're Arm employees — they want to see Arm tech used **correctly and deeply**
- They've been evangelizing KleidiAI, Performix, MCP server for months — recognize those names
- They'll appreciate when someone cites specific flags (`-march=armv9.2-a+sve2+i8mm+dotprod+bf16`) instead of vague "optimized for Arm"
- They want to be able to write a blog post about this on community.arm.com
- They will likely skim, not read every word — clarity matters more than volume

---

## Submission form field-by-field

### Project Overview (500 chars max)

Use the pitch from `01-PROBLEM-STATEMENT.md`:

> **NeuroSwarm-Arm is a self-evolving, cost-optimized multi-agent AI runtime built natively for Arm Neoverse.** Three-tier CPU-CPU speculative cascade (0.5B → 3B → 8B on NUMA-split Graviton5 cores), semantic MCP tool router (92% schema reduction), CXL-aware shared KV pool, and reasoning-token governor (60% fewer thinking tokens) — all tuned in closed loop by the Arm Performix MCP server. Result: ≥3.5× tokens/$ vs. H100 spot, one-line Helm deploy, reusable Helm chart + 6 MCP templates + Grafana dashboard. **Why it wins:** deepest Arm-specific kernel work (I8MM/SVE2/MTE), first Performix-driven evolution loop, novel CPU-CPU cascade inversion.

### Functionality / Output

Bullet the outputs the user gets when they run our project:

1. **Inference substrate** — llama.cpp + KleidiAI + vLLM INT4 with `-march=armv9.2-a+sve2+i8mm+dotprod+bf16`
2. **Speculative cascade** — three-tier CPU-CPU on NUMA-split cores
3. **Semantic MCP router** — FAISS + BGE-small, drops tool schema overhead by 92%
4. **Reasoning governor** — caps thinking tokens tied to tool confidence
5. **CXL-aware KV pool** — shared across agents, MTE-secured
6. **Cost-aware RL router** — PPO policy decides tier per request
7. **Performix-driven evolution loop** — closed-loop self-tuning via Arm MCP server
8. **Live Grafana dashboard** — tokens/sec, $/1M, cascade hit-rate, ARM PMU
9. **Helm chart** — one-command production deploy
10. **6 MCP server templates** — github, postgres, s3, slack, web-search, browser
11. **Migration guide** — x86/GPU → Arm cost calculator

### Setup Instructions

Link to `docs/setup.md`. In the field itself, give the 3-line version:

```bash
# On a Graviton5 instance (m9g.4xlarge or r8g equivalent)
git clone https://github.com/<you>/neuroswarm-arm && cd neuroswarm-arm
./install.sh                    # builds llama.cpp+KleidiAI, starts all services
helm install neuro ./helm/neuroswarm-arm
open http://localhost:3000      # Grafana dashboard
```

### Track Selection

**Track 2: Cloud AI** ✓

---

## README structure (GitHub repo root)

```markdown
# NeuroSwarm-Arm

> Self-evolving, cost-optimized multi-agent AI runtime for Arm Neoverse.
> 3.5× more tokens/$ than H100. Zero GPU required.

![banner](docs/img/banner.png)

## 🚀 Quick start (90 seconds)

\`\`\`bash
helm install neuro oci://ghcr.io/<you>/neuroswarm-arm/chart
\`\`\`

## 🏆 Why NeuroSwarm-Arm wins

[Link to 01-PROBLEM-STATEMENT.md]

## 🏗 Architecture

[Diagram from 02-ARCHITECTURE.md]

## 📊 Benchmarks (Arm Performix)

[6 screenshots from 05-BENCHMARK-PLAN.md]

| Metric | Baseline | NeuroSwarm-Arm | Source |
|---|---|---|---|
| Decode tok/s | 18 | 38 | Performix code-hotspots |
| TTFT (3k prompt) | 1.4s | 0.55s | KleidiAI I8MM path |
| ... | ... | ... | ... |

## 🛠 Setup

See [docs/setup.md](docs/setup.md).

## 🔄 Migrate from x86/GPU

See [docs/migrate-from-gpu.md](docs/migrate-from-gpu.md).

## 🎬 Demo

[YouTube link — <3 min]

## 📦 Reusable artifacts

- Helm chart: `helm/neuroswarm-arm/`
- Docker ARM64 image: `ghcr.io/<you>/neuroswarm-arm`
- 6 MCP server templates: `templates/mcp-servers/`
- Grafana dashboard: `helm/neuroswarm-arm/templates/grafana-dashboard.yaml`
- Migration guide: `docs/migrate-from-gpu.md`
- OKF knowledge graph example: `okf/`

## 🧪 Reproduce our benchmarks

\`\`\`bash
./benchmarks/run-all.sh    # runs all 5 Performix recipes + cascade + governor tests
\`\`\`

## 📄 License

Apache 2.0
```

---

## Demo video script (under 3 minutes)

**0:00–0:15 — Cold open**
> "$2.00 per agent request. 80% of that is waste. Waste from bloated tool schemas. Waste from duplicated KV caches. Waste from runaway thinking tokens. Today we're fixing all of it — on Arm."

**0:15–0:45 — Live demo (Graviton5 terminal)**
- Show real `kubectl`/`helm install neuro` running on terminal
- Show curl to agent API: streaming tokens
- Show the actual JSON tool schemas that come back — call out the schema bloat
- Show actual response with tool call

**0:45–1:30 — Dashboard tour**
- Open Grafana dashboard
- Walk through: tokens/sec, cost vs H100 ($0.61 vs $2.10), cascade hit rate donut, ARM PMU counters
- Show the live Performix hotspots list updating

**1:30–2:00 — Architecture fly-through**
- Quick animated diagram (5 layers + evolution loop)
- Highlight: NUMA split, KleidiAI I8MM path, MTE KV sharing, Performix MCP

**2:00–2:30 — Before/after Performix flame graph**
- Side-by-side: baseline (single llama.cpp) vs optimized (cascade)
- Show I8MM/SVE2 kernels appearing in optimized
- Show SIMD utilization 87%

**2:30–2:50 — Production deployment**
- Show Helm install one-liner
- Show 6 MCP server templates running
- Show the migration cost calculator: H100 $2.00 vs Graviton5 $0.61

**2:50–3:00 — Call to action**
- GitHub URL
- "Star us. Helm install us. Win your hackathon."

---

## Mapping deliverables to judging criteria

### Technological Implementation (40 pts)

**Strong signals to include:**
- [ ] Every build flag spelled out (`-march=armv9.2-a+sve2+i8mm+dotprod+bf16`)
- [ ] `apx recipe run` commands in README
- [ ] NUMA topology commands (`numactl --hardware`)
- [ ] Specific kernel names (`ggml_vec_dot_q4_K_M`, `sdot`, `smmla`)
- [ ] Cross-reference to Arm learning paths
- [ ] Type hints, tests, type-checked Python
- [ ] Production-shaped Helm chart (not a hack)
- [ ] CI passing on ARM64 runners (GitHub Actions)

**Auto-checked by judges:**
- Does it use KleidiAI? Yes (`-DGGML_CPU_KLEIDIAI=ON`)
- Does it use Arm Performix? Yes (5 recipes in `benchmarks/`)
- Does it use Arm MCP server? Yes (in evolution loop)
- Does it use llama.cpp? Yes (tier 1/2/3)
- Does it use ExecuTorch? Optional (in fallback path, mention)

### "WOW" Factor (25 pts)

**Wow moments to engineer:**
- Live demo of self-evolving prompts (commit changes, watch the dashboard numbers shift)
- Live cost comparison: watch the dollars-per-million-tokens counter while the H100 baseline number stays static
- Cascade hit-rate donut updating in real time
- Performix flame graph showing I8MM kernels lighting up

### Potential Impact (20 pts)

**Reusable artifacts (count them):**
1. Helm chart (1-command deploy)
2. Docker ARM64 image
3. 6 MCP server templates
4. Grafana dashboard JSON
5. Migration guide from x86/GPU
6. OKF knowledge graph seeds
7. OKF specification compliance
8. Prometheus scrape config
9. Performix recipe JSON files
10. Python library for cost-aware routing
11. C++ SVE2 JSON parser library
12. Mem0 OKF integration library

Each one is something a developer can copy-paste into their own project.

### UX / DX (15 pts)

**Clear first impression:**
- Banner image at top of README
- 3-line quick start above the fold
- Architecture diagram immediately visible
- Setup instructions work first try (tested on fresh instance)
- Demo video <3 min, captioned
- All error messages friendly and actionable

---

## Things judges will red-flag

**Avoid:**
- ❌ "Optimized for Arm" without specific flags
- ❌ Showing a single benchmark number with no baseline
- ❌ Mock-up screenshots instead of real terminal output
- ❌ Vague "uses AI" claims without naming the model + framework
- ❌ Repo without LICENSE file
- ❌ Broken Helm install (judges WILL run it)
- ❌ Demo video longer than 3 minutes (they'll skip)
- ❌ Spelling Performix wrong (it's Performix, not PerformX or Performics)

**Do:**
- ✅ Name the model: "Qwen2.5-0.5B-Instruct Q4_K_M"
- ✅ Name the framework: "llama.cpp + KleidiAI"
- ✅ Name the hardware: "AWS Graviton5 c9g.4xlarge"
- ✅ Name the ISA features: "SVE2 + I8MM + DotProd + BF16"
- ✅ Show real Performix screenshots
- ✅ Show real `helm install` output
- ✅ Spell Performix correctly (Performix, one word)

---

## The "I would blog about this" test

Before submitting, ask: would Arm's developer evangelists be excited to write a community.arm.com blog post about this? If yes, you win. If they have to scrape to find the Arm-specific value, you lose.

**Things that make it blog-worthy:**
1. **Novel inversion**: CPU-CPU speculative cascade (vs. GPU-first literature)
2. **First Performix integration**: wired into an agent runtime, not a one-shot benchmark
3. **MTE for AI**: first application to multi-agent KV sharing
4. **Closed-loop evolution**: GEPA + Performix is genuinely novel
5. **Real numbers**: 3.5× tokens/$, 92% schema reduction, 60% thinking reduction

If you can't check all 5, iterate before submitting.

---

## Submission checklist (final pre-flight)

- [ ] GitHub repo is **public**
- [ ] **LICENSE** file at root (Apache 2.0 or MIT)
- [ ] README has banner + quick start + architecture diagram + benchmark table
- [ ] `docs/setup.md` has step-by-step instructions tested on a fresh Graviton5
- [ ] `benchmarks/` directory has all 5 Performix recipe JSON outputs + screenshots
- [ ] `helm/neuroswarm-arm/` chart passes `helm lint`
- [ ] `templates/mcp-servers/` has 6 working MCP servers
- [ ] `docs/migrate-from-gpu.md` includes cost calculator
- [ ] Demo video uploaded to YouTube, public, <3 min, captioned
- [ ] Submission form: track = Cloud AI, all fields filled
- [ ] Tested fresh clone + install on a new instance in <90 seconds
- [ ] All claims in README traceable to a script in `benchmarks/`

---

## Post-submission

After Aug 14, while waiting for judges:
- Tweet the demo video with #ArmAIOptim hashtag
- Post on Hacker News (Show HN)
- Email Arm developer evangelists directly with a kind note
- Write a blog post on dev.to about the architecture

This maximizes chances of getting picked up by community.arm.com even if we don't win.