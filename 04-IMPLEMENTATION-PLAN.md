# Implementation Plan — Component by Component

> Every line of code you need to write, in the order you need to write it. 39 days, one week per layer.

---

## Week 1 (Jul 6–12) — Foundation

**Goal:** Stand up Graviton5 + working llama.cpp + KleidiAI + Arm Performix MCP end-to-end.

### Day 1-2: Provision & verify

```bash
# Launch Graviton5 (or fallback to Graviton4 if m9g not yet in your region)
aws ec2 run-instances \
  --image-id ami-0abcdef1234567890 \  # Ubuntu 24.04 ARM64
  --instance-type m9g.4xlarge \
  --region us-east-1 \
  --key-name my-key

ssh ubuntu@<ip>
uname -m                          # aarch64
grep -E '^(Features|sve2|i8mm|dotprod|bf16|asimd)' /proc/cpuinfo | sort -u
lscpu | grep -E '(Model name|Socket|Core|Thread|NUMA)'
numactl --hardware                # confirm 2 NUMA nodes
```

### Day 3-4: Build llama.cpp + KleidiAI

Use the Dockerfile from `03-TECH-STACK.md`. Verify:

```bash
./llama-cli --version
# Should report: built with KleidiAI, OpenMP, ARMv9.2

# Quick smoke test
./llama-cli -m /models/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf \
  -p "Hello, world" -n 64 -t 16

# Confirm I8MM activation
APX_LOG=debug ./llama-bench -m /models/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf -t 16
```

### Day 5-6: Install Arm Performix + MCP

```bash
# Download Arm Performix (free, requires Arm Developer account)
wget https://developer.arm.com/-/media/Files/downloads/performix/latest/performix-cli-linux-arm64.tar.gz
tar xzf performix-cli-linux-arm64.tar.gz -C /opt/

# Run system characterization
/opt/performix/bin/apx recipe run system-characterization \
  --target ssh://ubuntu@localhost \
  --output ./benchmarks/sys-char.json

# Install Arm MCP server (Docker)
docker pull arm/mcp:latest
docker run -d --name arm-mcp -p 8080:8080 \
  -e ARM_PERFORMIX_TARGET=ssh://ubuntu@localhost \
  arm/mcp:latest

# Test the MCP server from Python
pip install mcp-client
python -c "
from mcp import MCPClient
c = MCPClient('http://localhost:8080')
print(c.list_tools())  # should show apx_recipe_run, kb_search, etc.
"
```

### Day 7: First cascade prototype

Stand up two llama-server instances on different NUMA nodes:

```bash
# Tier 1 — drafter on NUMA 0
numactl --cpunodebind=0 --membind=0 \
  llama-server -m Qwen2.5-0.5B-Instruct-Q4_K_M.gguf \
  --port 8081 -ngl 0 -t 16 -c 4096 --host 0.0.0.0 &

# Tier 2 — verifier on NUMA 1
numactl --cpunodebind=1 --membind=1 \
  llama-server -m Llama-3.2-3B-Instruct-Q5_K_M.gguf \
  --port 8082 -ngl 0 -t 16 -c 8192 --host 0.0.0.0 \
  --model-draft-url http://localhost:8081 &

# Smoke test
curl -X POST http://localhost:8082/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cascade",
    "messages": [{"role":"user","content":"What is 2+2?"}],
    "stream": false
  }' | jq .
```

**End of Week 1 deliverable:** Working cascade with 1.8× speedup, validated by Performix.

---

## Week 2 (Jul 13–19) — Planes 1-3 (Inference substrate)

**Goal:** Cost router + reasoning governor + semantic MCP router + AQR.

### Day 8-9: Cost-aware RL router

```python
# neuroswarm/router.py
from dataclasses import dataclass
import numpy as np
from stable_baselines3 import PPO
from mem0 import MemoryClient

@dataclass
class PlanState:
    tool_confidence_top1: float
    kv_pressure: float          # 0..1
    slo_remaining_ms: float
    self_consistency_score: float
    cascade_tier_used: int
    cost_so_far_usd: float

class CostRouter:
    def __init__(self, mem0: MemoryClient):
        self.policy = PPO.load("policies/cost_router_v1.zip")
        self.mem0 = mem0

    def route(self, query: str, plan: PlanState) -> dict:
        obs = np.array([
            plan.tool_confidence_top1,
            plan.kv_pressure,
            plan.slo_remaining_ms / 1000,
            plan.self_consistency_score,
            plan.cost_so_far_usd / 0.10,  # normalize to $0.10 envelope
        ])
        action, _ = self.policy.predict(obs, deterministic=True)
        # action ∈ {0: tier1, 1: tier2, 2: tier3}
        return {"tier": int(action), "quant": self._pick_quant(plan)}

    def _pick_quant(self, plan: PlanState) -> str:
        if plan.tool_confidence_top1 > 0.85:
            return "Q4_0"  # speed
        return "Q5_K_M"   # quality
```

### Day 10-11: Reasoning-token governor

```python
# neuroswarm/governor.py
class ReasoningGovernor:
    def cap(self, plan: PlanState) -> int:
        cap = 4096
        if plan.tool_confidence_top1 > 0.85:
            cap = min(cap, 256)
        if plan.kv_pressure > 0.7:
            cap = min(cap, 512)
        if plan.slo_remaining_ms < 4000:
            cap = min(cap, int(256 + 4 * plan.tool_confidence_top1 * 1024))
        if plan.self_consistency_score > 0.9:
            cap = min(cap, 128)
        return cap

    def system_prompt(self, plan: PlanState) -> str:
        cap = self.cap(plan)
        return f"""You may reason for up to {cap} tokens before producing a tool call.
If your chosen tool has confidence ≥ 0.85 in the registry, commit immediately.
Use <commit/> when ready to emit the final answer."""
```

### Day 12-13: Semantic MCP tool router

```python
# neuroswarm/mcp_router.py
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

class SemanticMCPRouter:
    def __init__(self):
        self.encoder = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
        self.index = faiss.IndexFlatIP(384)
        self.tools = []

    def register(self, tool_def: dict):
        text = f"{tool_def['name']} {tool_def['description']} {' '.join(tool_def['params'].keys())}"
        emb = self.encoder.encode(text, normalize_embeddings=True)
        self.index.add(np.array([emb], dtype=np.float32))
        self.tools.append(tool_def)

    def route(self, query: str, k=3, threshold=0.42) -> list[dict]:
        q_emb = self.encoder.encode(query, normalize_embeddings=True)
        D, I = self.index.search(np.array([q_emb], dtype=np.float32), k=k)
        if D[0][0] < threshold:
            return self._rerank_by_param_sig(query, [self.tools[i] for i in I[0]])
        return [self.tools[i] for i in I[0]]
```

### Day 14: AQR — adaptive quant

```python
# neuroswarm/aqr.py
QUANT_BY_ROLE = {
    "reasoning": "Q5_K_M",
    "tool_call": "Q4_0",
    "summarization": "Q4_0",
    "code": "Q5_K_M",
    "classification": "Q4_0",
}

def pick_quant(agent_role: str, workload_class: str) -> str:
    return QUANT_BY_ROLE.get(agent_role, "Q5_K_M")
```

**End of Week 2 deliverable:** All four inference-plane optimizations running on real cascade. Performix code-hotspots recipe captured.

---

## Week 3 (Jul 20–26) — Planes 2 + 4 (Memory + Orchestration)

**Goal:** CXL KV pool + Mem0 + OKF + HAOE scheduler + MAKS sharing.

### Day 15-16: KVCacheMigrator (CXL software emulation)

```python
# neuroswarm/kv_migrator.py
import psutil
from pympler import asizeof

class KVCacheMigrator:
    def __init__(self, threshold_pct=70):
        self.threshold = threshold_pct
        self.local_pool = {}    # agent_id → KV pages in RAM
        self.cxl_pool = {}      # cold pages in CXL/RDMA

    def should_evict(self) -> bool:
        return psutil.virtual_memory().percent > self.threshold

    def evict_cold_pages(self, agent_id: str):
        if not self.should_evict():
            return
        cold = self._identify_cold_pages(agent_id)
        for page_id in cold:
            # Snapshot page table
            page = self.local_pool[agent_id].pop(page_id)
            # Compress + serialize
            compressed = zstandard.compress(page)
            # Write to RDMA-backed CXL pool (or NVMe)
            self._rdma_write(f"cxl://{agent_id}/{page_id}", compressed)

    def prefetch_likely_pages(self, agent_id: str, k=8):
        # Use Mem0 access-pattern prediction
        likely = self.mem0.predict_next_pages(agent_id, k=k)
        for page_id in likely:
            if page_id not in self.local_pool[agent_id]:
                self.local_pool[agent_id][page_id] = self._rdma_read(page_id)
```

### Day 17-18: Mem0 + OKF knowledge graph

```python
# neuroswarm/mem0_client.py
from mem0 import MemoryClient

class NeuroMemory:
    def __init__(self, agent_id: str):
        self.mem0 = MemoryClient()
        self.agent_id = agent_id
        self.okf_root = f"okf/{agent_id}/"

    def remember_fact(self, fact: str, metadata: dict = None):
        self.mem0.add(fact, user_id=self.agent_id, metadata=metadata)

    def recall(self, query: str, limit=5) -> list[str]:
        results = self.mem0.search(query, user_id=self.agent_id, limit=limit)
        return [r["memory"] for r in results]

    def load_okf(self, topic: str) -> str:
        # Progressive disclosure: read index, navigate, load only relevant
        index = open(f"{self.okf_root}/index.md").read()
        # ... navigate to topic
        return relevant_md
```

### Day 19-20: HAOE scheduler (SVE2 JSON parsing)

```c
// neuroswarm/native/json_sve2.c
#include <arm_sve.h>
#include <jsmn.h>

size_t json_parse_sve2(const char* json, size_t len, jsmntok_t* tokens, size_t max_tokens) {
    size_t i = 0, n = 0;
    while (i < len && n < max_tokens) {
        // Vectorized skip-whitespace using SVE2
        svbool_t pg = svwhilelt_b8(i, (uint32_t)len);
        svuint8_t chunk = svld1_u8(pg, (uint8_t*)(json + i));
        // ... find next structural char
        // Use SVE2 MATCH for { } [ ] : , detection
    }
    return n;
}
```

```python
# neuroswarm/haoe.py
import ctypes
from concurrent.futures import ProcessPoolExecutor

class HAOEScheduler:
    def __init__(self, fast_cores=16, slow_cores=32):
        self.fast_cores = list(range(fast_cores))
        self.slow_cores = list(range(fast_cores, fast_cores + slow_cores))
        self.work_stealing_queues = {i: deque() for i in range(fast_cores + slow_cores)}

    def schedule(self, agent_task: Callable, priority: str = "normal"):
        cores = self.fast_cores if priority == "critical" else self.slow_cores
        target_core = self._find_idle_core(cores)
        # Bind to NUMA-local memory
        return self._submit_numa_aware(agent_task, target_core)
```

### Day 21: MAKS — MTE-tagged KV sharing

```c
// neuroswarm/native/mte_kv.c
#include <arm_mte.h>

void* mte_share_kv(void* kv_page, size_t size, uint8_t producer_tag) {
    // Tag all bytes in this KV page with producer agent_id
    uint64_t* p = (uint64_t*)kv_page;
    for (size_t i = 0; i < size / 8; i++) {
        __arm_mte_tag_and_set(p + i, producer_tag);
    }
    return kv_page;
}

void* mte_read_foreign_kv(void* kv_page, size_t size) {
    // Increment tag = declare foreign read access
    __arm_mte_increment_tag();
    return kv_page;  // MTE hardware verifies the increment is valid
}
```

**End of Week 3 deliverable:** All memory + orchestration layers running. 200k-token agent session survives worker restart.

---

## Week 4 (Jul 27–Aug 2) — Plane 5 (Evolution loop)

**Goal:** Arm Performix ASI → official-aligned GEPA **text** evolution + cost dashboard.

> GEPA optimizes prompts/OKF/tool text only (Genetic-Pareto). Numeric cascade knobs use RuleBased AROP — not GEPA. See `docs/arop/gepa.md`.

### Day 22-23: Performix-driven GEPA text evolution

```python
# neuroswarm_arm/evolution/reflection/gepa/
from neuroswarm_arm.evolution.reflection.gepa import (
    GEPAFacade, ApprovalGate, TextArtifactDeployer, ASIBuilder,
)

facade = GEPAFacade()
asi = ASIBuilder().build(observations=[...], profiling_asi=performix_asi)
facade.reflect(asi=asi)
result = facade.run_local_loop(
    {"system_prompt": seed, "governor_policy": gov_md},
    trainset=eval_batch,
)
# Never auto-deploy — ApprovalGate required
gate = ApprovalGate()
gate.submit(result.best)
gate.approve(result.best.id)
TextArtifactDeployer(okf_root="okf", memory=mem0).deploy(
    result.best.mark_approved(), gate=gate
)
```

### Day 24-25: Cost dashboard (Grafana + Prometheus)

```yaml
# helm/neuroswarm-arm/templates/grafana-dashboard.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: neuroswarm-dashboard
data:
  dashboard.json: |
    {
      "panels": [
        {"title": "Tokens/sec (live)", "type": "graph", "datasource": "Prometheus"},
        {"title": "Cost per 1M tokens vs H100", "type": "stat"},
        {"title": "Cascade hit-rate", "type": "piechart"},
        {"title": "KV cache dedup ratio", "type": "gauge"},
        {"title": "Thinking tokens/query", "type": "graph"},
        {"title": "ARM PMU: SIMD util", "type": "stat"},
        {"title": "Performix hotspots top-10", "type": "table"}
      ]
    }
```

### Day 26-27: 6 MCP server templates

For each of github, postgres, s3, slack, web-search, browser:

```python
# templates/mcp-servers/github/server.py
from fastmcp import FastMCP

mcp = FastMCP("github")

@mcp.tool()
def list_issues(repo: str, state: str = "open", limit: int = 10) -> list[dict]:
    """List GitHub issues for a repository."""
    # ... actual implementation
    return issues

@mcp.tool()
def search_code(query: str, repo: str = None) -> list[dict]:
    """Search code across GitHub."""
    # ...

if __name__ == "__main__":
    mcp.run()
```

### Day 28: AWPP pre-warm predictor (PPO)

```python
# neuroswarm/prewarm.py
class AWPP:
    def __init__(self, mem0):
        self.mem0 = mem0
        self.model = PPO.load("policies/prewarm_v1.zip")
        self.cache_state = {}  # model_id → is_warm

    def predict_next_models(self, agent_id: str, horizon_s: int = 5) -> list[str]:
        history = self.mem0.get_recent_workflow(agent_id, limit=20)
        state = self._encode_state(history, horizon_s)
        action, _ = self.model.predict(state, deterministic=True)
        return self._decode_action(action)

    def prewarm(self, model_ids: list[str]):
        for mid in model_ids:
            if not self.cache_state.get(mid, False):
                # Send HEAD request to llama-server to load weights into L3
                requests.get(f"http://tier-{mid}:8080}/warmup")
                self.cache_state[mid] = True
```

**End of Week 4 deliverable:** Evolution loop running nightly, dashboard live, all 6 MCP templates working.

---

## Week 5 (Aug 3–9) — Polish + benchmark

**Goal:** Helm chart, Docker ARM64 image, README, demo video, final benchmarks.

### Day 29-30: Helm chart + Docker

```bash
# Multi-arch Docker build
docker buildx create --use --name arm-builder
docker buildx build --platform linux/arm64 \
  -t neuroswarm/arm:latest \
  --load .

# Lint + package Helm chart
helm lint ./helm/neuroswarm-arm
helm package ./helm/neuroswarm-arm
```

### Day 31-32: README + migration guide

```markdown
# NeuroSwarm-Arm

Self-evolving, cost-optimized multi-agent AI runtime for Arm Neoverse.

## Quick start (90 seconds)

```bash
helm install neuro oci://registry-1.docker.io/neuroswarm/chart \
  --set graviton.instanceType=m9g.4xlarge
```

Open http://localhost:3000 → Grafana dashboard.
Open http://localhost:8000 → API playground.

## Why

[Pitch from 01-PROBLEM-STATEMENT.md]

## Architecture

[Diagram from 02-ARCHITECTURE.md]

## Setup

See [docs/setup.md](docs/setup.md).

## Migration from x86/GPU

See [docs/migrate-from-gpu.md](docs/migrate-from-gpu.md).
```

### Day 33-34: Final Performix benchmarks

```bash
# Baseline run (single llama.cpp, no cascade)
apx recipe run code-hotspots --binary /usr/local/bin/llama-server --output baseline.json

# Optimized run (full NeuroSwarm-Arm)
apx recipe run code-hotspots --binary /usr/local/bin/neuroswarm-router --output optimized.json

# Generate comparison report
apx recipe compare --baseline baseline.json --optimized optimized.json --output COMPARISON.md
```

### Day 35: Demo video

3-minute video script:
- 0:00 — Cold open: "$2.00 per agent request. 80% is waste."
- 0:15 — Quick demo: live query, show tokens streaming
- 0:45 — Dashboard tour: cascade hit rate, cost vs H100, PMU
- 1:30 — Architecture fly-through (animated)
- 2:00 — Performix flame graph comparison (before/after)
- 2:30 — One-line Helm install
- 2:50 — Call to action / GitHub link

**End of Week 5 deliverable:** Everything ready for submission.

---

## Week 6 (Aug 10–14) — Submit

### Day 36-37: Submission write-up

Use the content from `01-PROBLEM-STATEMENT.md` directly:
- Project Overview (1 paragraph pitch)
- Functionality / Output (what it does)
- Setup Instructions (link to docs/setup.md)

### Day 38: Final dry-run

```bash
# Fresh clone test on a new Graviton5 instance
git clone https://github.com/<you>/neuroswarm-arm.git
cd neuroswarm-arm
./install.sh
# Time it — must complete in <90 seconds
```

### Day 39: Submit

Submit Aug 13, leaving Aug 14 as buffer. **Do not** wait until Aug 14 — judges get tired, Devpost may have issues.

---

## Risk register (what could go wrong)

| Risk | Probability | Mitigation |
|---|---|---|
| Graviton5 not available in region | Medium | Fall back to Graviton4 c8g.4xlarge — all code paths work |
| Arm Performix MCP server has bugs | Medium | Manual Performix CLI as fallback, MCP integration is a feature not a dependency |
| Cascade acceptance rate low on real queries | Low | Self-speculation (no draft model) as fallback |
| Mem0 namespace issues | Low | Local fallback to plain FAISS + Mem0 self-hosted |
| CXL emulation slow | High | Document expected ~6 µs latency, use NVMe pager for demo |
| Demo video too long | Low | Script it strictly, cut ruthlessly |
| Submitting on deadline day | High | Submit Aug 13, period |