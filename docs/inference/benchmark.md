# Benchmark Guide

## Unit / stress

```bash
pytest tests/runtime/dipa/test_control_plane.py tests/runtime/dipa/test_inference_stress.py -q
```

## llama-bench (inside KleidiAI image)

```bash
docker compose run --rm tier2 llama-bench -m /models/llama-3.2-3b-q5_k_m.gguf -t $(nproc)
```

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

