# NEXUS-ARM Inference Architecture

Production inference substrate for NEXUS-ARM. DIPA is the Inference Runtime Kernel (Layer 2). ARMORA is the only developer-facing facade.

## Layers

```text
ARMORA (load_model/generate/stream/warmup/metrics/health/shutdown)
   → DIPARuntime + control plane managers
      → ASCR (ArmCascade Adaptive Speculative Cascade Runtime) / ExecutionPipeline
         → InferenceBackend HAL
            → llama.cpp (managed KleidiAI server) | vLLM | SGLang | ExecuTorch | LiteRT | rtp-llm
```

Peers (connectors only): AQR, AWPP, MAKS, RTG. HAOE never imports llama.cpp.

ASCR docs: [`docs/armcascade/`](../armcascade/README.md). ADR: [`docs/dipa/adr/0008-ascr-replaces-heuristic-cascade.md`](../dipa/adr/0008-ascr-replaces-heuristic-cascade.md).

## Process model

llama.cpp runs as **managed server processes** (Docker / ProcessSupervisor). NEXUS owns build flags, affinity, readiness, and KleidiAI log verification (`CPU_KLEIDIAI`). No in-process GGML embed in v1.

## Control plane managers

ModelManager, BackendManager, InferenceScheduler, RequestQueue, StreamingEngine, KVCacheManager, WarmupManager, TokenizerManager, MetricsCollector, HealthService, ConfigurationManager, LifecycleManager, BenchmarkRunner, ThreadAffinityManager, HardwareDetector, TelemetryExporter.

Boot order: detect → affinity → backends → models → warmup → ready.

## Axion honesty

GCP Axion = Neoverse V2. Detect SVE2/DotProd/I8MM/BF16 at runtime. Do not hardcode Neoverse V3. SME auto via `GGML_KLEIDIAI_SME` unset. NUMA often single-node — affinity is best-effort.
