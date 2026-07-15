# Benchmark Plan — Prove Every Claim

> Every number in the pitch must be reproducible. Here's how.

---

## Required: Arm Performix recipes

The hackathon explicitly says: *"Developers can use Arm Performix to get exact benchmarks of their Arm-based performance and be able to clearly show their results."*

We run **5 recipes** minimum:

### Recipe 1: System Characterization

```bash
apx recipe run system-characterization \
  --target ssh://ubuntu@<graviton5-ip> \
  --output ./benchmarks/01-sys-char.json
```

**Captures:** Memory bandwidth, L3 latency, NUMA topology, sustained FLOPs.
**Why judges care:** Establishes we're on real Arm silicon, not a mock.

### Recipe 2: Code Hotspots (the headline number)

```bash
# Baseline (single llama.cpp, no cascade)
apx recipe run code-hotspots \
  --binary /usr/local/bin/llama-server \
  --duration 60 \
  --output ./benchmarks/02-hotspots-baseline.svg

# Optimized (NeuroSwarm-Arm)
apx recipe run code-hotspots \
  --binary /usr/local/bin/neuroswarm-router \
  --duration 60 \
  --output ./benchmarks/02-hotspots-cascade.svg
```

**Captures:** Flame graph showing where time is spent.
**What we expect to see:**
- Baseline: ~85% time in `ggml_vec_dot_q4_K_M`, no SIMD utilization
- Cascade: ~60% in ggml (less work per request), visible I8MM kernels (`sdot`, `smmla`), SVE2 SIMD ~87% util

### Recipe 3: CPU Microarchitecture (top-down)

```bash
apx recipe run cpu-microarch \
  --binary /usr/local/bin/neuroswarm-router \
  --output ./benchmarks/03-topdown.svg
```

**Captures:** Pipeline stalls, branch mispredicts, memory-bound vs. compute-bound.
**What we expect to see:** Decode phase dominates with memory-bound stalls (validates cascade theory — single-batch decode IS memory-bound on Arm).

### Recipe 4: System Utilization (multi-agent load)

```bash
apx recipe run system-utilization \
  --attach-pid $(pgrep -f neuroswarm-router) \
  --duration 300 \
  --output ./benchmarks/04-system-util.svg
```

**Captures:** 192-core utilization under 10 concurrent agents.
**What we expect to see:** HAOE scheduler puts critical-path agents on fast cores (cores 0-15), background tasks on cores 16-191. NUMA-aware work-stealing visible.

### Recipe 5: Comparison report

```bash
apx recipe compare \
  --baseline ./benchmarks/02-hotspots-baseline.json \
  --optimized ./benchmarks/02-hotspots-cascade.json \
  --output ./benchmarks/05-COMPARISON.md
```

**Output:** Markdown table we paste directly into the submission.

---

## Token economics benchmark

We need to prove **3.5× tokens/$, not just "fast".**

```bash
# Standard agent workload: 1000 requests, mixed complexity
python ./benchmarks/agent_workload.py \
  --instances 10 \
  --requests-per-instance 100 \
  --output ./benchmarks/economics.json
```

Measures per-request:
- Input tokens
- Output tokens (visible + thinking)
- Wall-clock latency
- Cost (Arm: $0.5243/hr for c8g.4xlarge at $0.0001456/vCPU-s)

Then:
- **H100 spot baseline:** $2.00 per 1M tokens (published industry average)
- **NeuroSwarm-Arm:** computed from our JSON

---

## Cascade acceptance rate benchmark

```python
# benchmarks/cascade_acceptance.py
results = []
for prompt in test_prompts:  # 500 diverse agent prompts
    draft = tier1.generate(prompt, k=5)
    accepted = tier2.verify(draft)
    results.append({"prompt": prompt, "accepted": accepted})

acceptance_rate = sum(r["accepted"] for r in results) / len(results)
print(f"Cascade acceptance: {acceptance_rate:.1%}")
# Target: ≥70%
```

---

## Semantic router accuracy

Use MCPGA ground truth:

```python
# benchmarks/router_accuracy.py
from mcpga import MCPGADataset  # public eval

dataset = MCPGADataset()
correct = 0
for q, ground_truth_tools in dataset:
    predicted = router.route(q, k=3)
    if any(t.id in ground_truth_tools for t in predicted):
        correct += 1

print(f"Top-3 accuracy: {correct/len(dataset):.1%}")
# Target: ≥95% (vs ~91.5% baseline per MCPGA paper)
```

---

## Reasoning-token governor

```python
# benchmarks/governor.py
results_uncontrolled = run_deepseek_r1(prompts, max_thinking=8192)
results_governed = run_deepseek_r1(prompts, max_thinking=governor.cap(plan))

print(f"Uncontrolled avg thinking tokens: {mean(r.thinking for r in results_uncontrolled)}")
print(f"Governed avg thinking tokens:     {mean(r.thinking for r in results_governed)}")
print(f"Accuracy delta: {accuracy(results_governed) - accuracy(results_uncontrolled):+.1%}")
# Target: ~60% fewer tokens, ≤2% accuracy drop
```

---

## KV cache survival test

```bash
# benchmarks/kv_survival.sh
# 1. Start agent with 200k-token session
python ./benchmarks/long_session.py --tokens 200000 --output session.json &

# 2. Wait until session.json has full KV
sleep 300

# 3. Kill the worker
pkill -f "long_session.py"

# 4. Restart — verify session.json resumes seamlessly
python ./benchmarks/resume_session.py --from session.json
# Target: zero copy of pre-kill KV, resumes mid-conversation
```

---

## Self-speculation speedup

```bash
# Use llama.cpp --spec-self
./llama-cli -m Llama-3.1-8B-Q5_K_M.gguf \
  --spec-self ngram-map-k \
  --spec-ngram-size-n 24 \
  --draft-min 12 --draft-max 48 \
  -p "$(cat agent_prompts.jsonl)" \
  -n 512 > output_self_spec.txt

# Compare to baseline (no spec)
./llama-cli -m Llama-3.1-8B-Q5_K_M.gguf \
  -p "$(cat agent_prompts.jsonl)" \
  -n 512 > output_baseline.txt
```

---

## Helm install time

```bash
time helm install neuro ./helm/neuroswarm-arm
# Target: <90 seconds from `helm install` to dashboard accessible
```

---

## AROP Plane 5 (policy optimization loop)

```bash
python benchmarks/arop/run_benchmark.py
pytest tests/runtime/evolution -q
# Optional live: POST /arop/optimize  (NSA_AROP_PERFORMIX=0 for CI mocks)
```

**Captures:** candidate vs baseline reward, canary/rollback decisions, policy registry status.
**Note:** NEXUS Layer 5 = MAKS; AROP = Plane 5. Never claim Performix wins without `NSA_AROP_PERFORMIX=1` + real `apx` output.

---

## Final benchmark dashboard (the screenshots)

Six PNGs we put in the submission README:

1. `benchmarks/screenshots/01-sys-char.png` — System characterization
2. `benchmarks/screenshots/02-hotspots-baseline.png` — Baseline flame graph
3. `benchmarks/screenshots/03-hotspots-cascade.png` — Optimized flame graph
4. `benchmarks/screenshots/04-cascade-hit-rate.png` — Donut: 71% / 23% / 6%
5. `benchmarks/screenshots/05-cost-dashboard.png` — Live Grafana
6. `benchmarks/screenshots/06-arm-vs-gpu.png` — Tokens/$ bar chart

---

## The headline claim ledger

| Claim | How we prove it |
|---|---|
| 1.8–2.3× cascade speedup | llama-bench + Performix code-hotspots |
| 60–80% orchestration latency reduction (HAOE) | Performix system-utilization recipe |
| 92% tool schema reduction | Token count: 143k → 11k, measured |
| +5% tool selection accuracy | MCPGA ground-truth benchmark |
| 60% fewer thinking tokens | Governor benchmark, accuracy delta verified |
| 2× more concurrent agents | KV cache dedup + MTE measurement |
| ≥3.5× tokens/$ vs. H100 | Live cost dashboard + H100 spot baseline |
| 200k-token session survival | KV survival test script |
| Cold-start ~150ms vs ~600ms | End-to-end latency benchmark |

Every claim has a script. Every script outputs JSON. Every JSON becomes a screenshot or a number in the README.

---

## What we DON'T claim (and why)

| Don't claim | Why |
|---|---|
| "Best in class" / "fastest" | Relative claims need baselines that don't exist |
| "10× speedup" | Best documented Arm number is 2.5× TTFT — 10× is hype |
| "Replaces all GPUs" | DIPA optional GPU offload — we augment, not replace |
| "Zero cost" | Mem0 marketing cites high reduction; we report measured compression_ratio / retention |
| "Production ready" | It's a hackathon project, but production-shaped |

Under-promise, over-deliver. The judges will respect numbers they can verify.