# Benchmark Guide

## Overhead bound

Mock provider path must stay cheap:

```bash
pytest tests/armora/profiling/test_rpf.py::test_benchmark_overhead_bound -q
```

Asserts 50 open/sample/finalize cycles complete in under 5s.

## Provider evidence

| Claim | Evidence |
|-------|----------|
| Performix used | `profiler_used=performix` + recipe JSON under `work/profiling/performix/` |
| perf counters | Linux + `perf` + non-zero `hardware.cycles` |
| psutil | `memory.rss_bytes` > 0 in profile |
| Cascade honesty | `rpf.capabilities()` reports AVAILABLE/UNAVAILABLE |

## Production mode

Default `NSA_RPF_MODE=production` → low `NSA_RPF_SAMPLE_HZ` (1).

Benchmark mode:

```bash
export NSA_RPF_MODE=benchmark
export NSA_RPF_SAMPLE_HZ=10
export NSA_RPF_PROVIDER=perf   # or performix when available
```

Never claim Performix / PMU / SVE2 wins without matching capability + artifacts.
