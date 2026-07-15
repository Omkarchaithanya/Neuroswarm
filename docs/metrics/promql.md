# PromQL Examples

## RED

```promql
sum(rate(nexus_request_total[1m]))
sum(rate(nexus_request_failed_total[1m])) / clamp_min(sum(rate(nexus_request_total[1m])), 1)
histogram_quantile(0.95, sum(rate(nexus_request_duration_seconds_bucket[5m])) by (le))
```

## Recording-rule consumers

```promql
nexus:request_duration_seconds:p95_5m
nexus:request_duration_seconds:p99_5m
nexus:planner_accuracy:avg5m
nexus:backend_efficiency:ratio5m
```

## USE (HAOE / hardware)

```promql
nexus_haoe_queue_depth
avg(nexus_haoe_worker_utilization)
avg(nexus_hw_cpu_usage)
```

## Inference

```promql
histogram_quantile(0.95, sum(rate(nexus_dipa_prefill_latency_seconds_bucket[5m])) by (le))
sum(rate(nexus_dipa_speculative_acceptance_total[5m]))
/
clamp_min(
  sum(rate(nexus_dipa_speculative_acceptance_total[5m]))
  + sum(rate(nexus_dipa_speculative_rejection_total[5m])),
  1
)
```

## FinOps

```promql
avg(nexus_cost_per_request)
avg(nexus_tokens_per_dollar)
min by (dim) (nexus_budget_remaining)
```

## KV

```promql
nexus_kv_cache_reuse
sum(rate(nexus_kv_cache_hits_total[5m])) /
clamp_min(sum(rate(nexus_kv_cache_hits_total[5m])) + sum(rate(nexus_kv_cache_misses_total[5m])), 1)
```
