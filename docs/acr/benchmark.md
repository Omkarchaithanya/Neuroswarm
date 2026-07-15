# ACR Benchmarks

Measure (never hardcode a target %):

- compression_ratio, token_reduction, information_retained
- planning / retrieval / compression / assembly latency
- cache hit ratio, version overhead
- NUMA locality (skip if single node)
- memory footprint, throughput

```bash
python -m benchmarks.acr.bench_acr --budget 1000 --repeat 20
```

Results: `benchmarks/results/acr_bench.json`
