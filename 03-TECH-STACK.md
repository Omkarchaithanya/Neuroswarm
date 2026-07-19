# Tech Stack — Concrete Tools & Flags

> Axion-first. Copy-paste ready. No invented Performix recipes. No `arm/mcp:latest` Docker tag.

---

## Hardware target

| Priority | Host | Notes |
|---|---|---|
| **Primary (demo)** | GCP Axion `c4a-standard-8` | Neoverse-V2, 8 vCPU / 32 GB, 1 NUMA, SVE2/I8MM/BF16 |
| Optional scale-up | Graviton4/5 multi-NUMA | Where NUMA-split + CXL activate |
| Future | Arm AGI CPU / native CXL | Documented capability, not hackathon dependency |

**Option A:** auto-detect NUMA/CXL/MTE; degrade on Axion; activate on multi-socket Neoverse.

---

## Software inventory

### Build / runtime
| Component | Notes |
|---|---|
| Ubuntu 24.04 aarch64 | Axion image |
| Python 3.12 + **uv** | `uv sync --all-groups` |
| Docker Compose | MVP path |
| Helm `neuroswarm-arm` | K8s path |

### Inference
| Component | Image / flag |
|---|---|
| **llama.cpp + KleidiAI** | `nexus-arm/llama-kleidiai:server` (`GGML_CPU_KLEIDIAI=ON`) — see `docker/Dockerfile.llama-kleidiai` |
| Stock baseline (A/B only) | `ghcr.io/ggml-org/llama.cpp:server` |
| **SGLang CPU (optional `pd`)** | `${NSA_SGLANG_IMAGE:-lmsysorg/sglang:latest}` + `SGLANG_USE_CPU_ENGINE=1`. Confirm **linux/arm64** manifest includes Arm Neoverse W8A8 work ([Arm blog May 2026](https://developer.arm.com/community/arm-community-blogs/b/ai-blog/posts/bringing-sglang-high-performance-llm-inference-to-arm-neoverse)). Pin digest if `:latest` drifts. |

### Profiling (REQUIRED)
| Component | Correct reference |
|---|---|
| Arm Performix | https://developer.arm.com/servers-and-cloud-computing/arm-performix |
| `apx` CLI | install via `scripts/install-performix.sh` |
| Docker MCP image | **`armlimited/arm-mcp:latest`** (NOT `arm/mcp:latest`) |
| GitHub repo | https://github.com/arm/mcp |
| Product AROP bridge | Compose profile `performix` → `performix-bridge` wrapping host `apx` |

### GA Performix recipes (Apr 2026)

```text
code_hotspots
cpu_microarchitecture
instruction_mix          # proves Kleidi / SVE2 / I8MM
memory_access
system_characterization  # preview (ASCT)
```

**Do not use:** `system-utilization` (invented).  
Normalize aliases in `neuroswarm_arm/evolution/performix_client.py`.  
Capture: `bash performix_capture.sh` (uses `PerformixClient`, not fake `--output` flags).

```bash
apx recipe list   # always re-verify IDs on your apx version
bash performix_capture.sh
COMPARE=1 bash performix_capture.sh
```

### Memory / routing / obs
Mem0, OKF, TurboVec router, Prometheus, Grafana, OpenTelemetry collector — see Compose + `ops/`.

---

## KleidiAI deploy (pass gate)

```bash
bash scripts/deploy-kleidiai-tiers.sh
# docker compose ps must show nexus-arm/llama-kleidiai:server on tier1/2/3
PROJECT_ROOT=~/neuroswarm-arm bash scripts/capture-evidence.sh
```

---

## Helm

```bash
helm upgrade --install neuroswarm ./helm/neuroswarm-arm \
  --set image.llama=nexus-arm/llama-kleidiai:server
```

Time a real cluster install (not just `helm lint`). Target &lt;90s chart apply where cluster is warm.

---

## Checklist

- [ ] `NSA_LLAMA_IMAGE=nexus-arm/llama-kleidiai:server` in `.env`
- [ ] Performix `instruction_mix` artifact in `docs/evidence/performix/`
- [ ] Docs say `armlimited/arm-mcp:latest` for Docker
- [ ] SGLang arm64 verified before pd-profile claims
- [ ] Pitch = Axion + Option A (not Graviton5-as-demo)
