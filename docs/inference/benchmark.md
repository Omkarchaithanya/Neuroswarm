# Benchmark Guide

## Unit / stress

```bash
pytest tests/runtime/dipa/test_control_plane.py tests/runtime/dipa/test_inference_stress.py -q
```

## llama-bench (inside KleidiAI image)

```bash
# One-shot
docker compose run --rm --entrypoint llama-bench tier2 \
  -m /models/xLAM-2-3B-fc-r-Q4_0.gguf -t $(nproc)

# Matrix sweep → work/profiling/llama-bench-*.json
TIER=2 bash scripts/run-llama-bench-sweep.sh
```

See also [llama-native.md](../profiling/llama-native.md) for completion `timings` capture and tier `/metrics`.
## Cascade acceptance

```bash
python benchmarks/run_all.py
```

## Control-plane harness

```python
from neuroswarm_arm.runtime.dipa import build_dipa
rt = build_dipa(use_mock=True)
print(rt.benchmark_runner.run("gen", lambda: rt.engine.generate([{"role":"user","content":"x"}], max_tokens=8), iterations=5))
rt.shutdown()
```

## PD soft mode (mock)

```bash
pytest tests/runtime/dipa/pd/ -q
python benchmarks/pd_suite.py --pd-mode soft --iterations 5
```

Metrics of interest: `dipa_prefix_hit_ratio`, `dipa_recompute_tokens`, `dipa_prefill_ms`, `dipa_chunk_count`, `dipa_kv_transfer_mode`.

Live compose profile:

```bash
docker compose --profile pd up -d
export NSA_DIPA_PD_MODE=soft
```

Evidence for KleidiAI: capture tier logs containing `CPU_KLEIDIAI`.

