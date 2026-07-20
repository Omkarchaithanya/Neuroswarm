# Axion evidence capture — status

status: captured  
host: GCP Axion c4a-standard-8 (aarch64, Neoverse-V2, 1 NUMA)  
image: nexus-arm/llama-kleidiai:server (`GGML_CPU_KLEIDIAI=ON`)  
captured_at: 2026-07-18

## Pass gates

- [x] KleidiAI IMAGE on tier1/2/3 (not `ghcr.io/ggml-org/llama.cpp:server`)
- [x] `run_all.json` status=ok
- [x] non-empty `prometheus-metrics.txt`
- [x] live chat-completion from cascade
- [x] Performix `code_hotspots` + `instruction_mix` under `../performix/`
- [x] SGLang arm64 manifest verified (`SGLANG-ARM64.md`)
- [x] Helm lint/template/apply timed (`HELM-TIMING.md`)
- [x] MCP 6/6 templates (`MCP-TEMPLATES.md`)

## Reproduce

```bash
bash scripts/deploy-kleidiai-tiers.sh
uv sync
bash scripts/capture-evidence.sh
sudo apt-get install -y python3-venv
NSA_PERFORMIX_ALLOW_DEMO=0 bash performix_capture.sh
bash scripts/verify-sglang-arm64.sh
```
