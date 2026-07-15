# ASCR Configuration Guide

## Files

| File | Purpose |
|------|---------|
| `runtime/armcascade/config/ascr.yaml` | Master defaults, confidence weights, ARM, telemetry |
| `strategies.yaml` | Enable/disable proposers & verifiers |
| `tiers.yaml` | Tier backends/roles (draft/verify/escalate) |
| `escalation_graphs.yaml` | Named DAGs |
| `runtime/dipa/config/cascade.yaml` | Merged into ASCR via `build_ascr(dipa_cascade_cfg=...)` |

## Environment

| Variable | Effect |
|----------|--------|
| `NSA_ASCR_ENABLED` | Master enable hint |
| `NSA_ASCR_DEFAULT_PROPOSER` | Override proposal strategy |
| `NSA_ASCR_DEFAULT_VERIFIER` | Override verify strategy |
| `NSA_ASCR_DRAFT_LEN` | Base draft length |
| `NSA_ASCR_ACCEPT_THRESHOLD` | Base accept τ |
| `NSA_ASCR_GRAPH` | Escalation graph name |
| `NSA_ASCR_QUALITY_FALLBACK` | Degrade when logits missing |
| `NSA_CASCADE_CONFIDENCE_THRESHOLD` | Legacy; merged into accept threshold |

## Example `ascr` block in cascade.yaml

```yaml
ascr:
  enabled: true
  strategy: draft_model
  verify_strategy: block
  graph: default_linear
```

## Escalation graphs

Conditions: `always`, `high_confidence`, `low_confidence`, `tool_needed`, `memory_needed`.

Node kinds: `tier`, `tool`, `memory`, `accept`, `terminal`.
