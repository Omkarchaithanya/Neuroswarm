# Draft Model Registry

> Gap **G18** — pair target (tier2) models with host-arch-appropriate draft models.

## Overview

`DraftModelProposer` historically always used the `tier1` backend as the draft.
The registry maps `(target_model, host_arch) → (draft_path, draft_quant)` so Axion
and Apple hosts pick a smaller sibling draft without hard-coding a single model.

Resolution order in `DraftModelProposer.initialize`:

1. `NSA_DRAFT_MODEL_PATH` (optional override) + `NSA_DRAFT_QUANT` (default `Q4_0`)
2. `DraftModelRegistry.resolve(target, host_arch)` when
   `strategies.draft_registry.enabled` and/or `NSA_DRAFT_REGISTRY_AUTO=1`
3. Else keep `tier1` (previous behaviour)

Backend wiring stays `tier1` unless config already has `role: draft`. The
resolved identity is attached to proposal metadata (`draft_path`, `draft_quant`,
`host_arch`, `target_model`) for ops/compose override — it does not load a new
heavy weight path by itself.

## Host architectures

| Value | Meaning |
|-------|---------|
| `neoverse-v2` | Axion / C4A (SVE2+I8MM+ASIMDDP via `probe_cpu_features`) |
| `neoverse-v3` | SME2 present |
| `apple-m` / `apple-pro` / `apple-max` | Darwin `hw.model` heuristics |
| `x86` | Everything else |

Override with `NSA_HOST_ARCH=...`. Target id from `NSA_TARGET_MODEL` or the
tier with `role: target` (else first non-draft tier model).

## Default pairs

| Target | Host | Draft | Quant |
|--------|------|-------|-------|
| Qwen2.5-3B-Instruct-4bit | neoverse-v2 / v3 / apple-m | Qwen2.5-0.5B-Instruct-4bit | Q4_0 |
| Llama-3.2-3B-Instruct-4bit | neoverse-v2 / v3 / apple-* | Llama-3.2-1B-Instruct-4bit | Q4_0 |
| SmolLM2-1.7B-Instruct-4bit | neoverse-v2 / v3 | SmolLM2-135M-Instruct-4bit | Q4_0 |

On Axion, prefer KleidiAI 4-bit paths for both target and draft (ARM-TRUTHY).

## Extending

### Code table

Edit `PAIRS` in
[`neuroswarm_arm/runtime/armcascade/proposal/draft_registry.py`](../../neuroswarm_arm/runtime/armcascade/proposal/draft_registry.py).

### Config overlay

```yaml
# strategies.yaml or top-level draft_registry
draft_registry:
  enabled: true
  pairs:
    "MyTarget-7B-4bit|neoverse-v2":
      draft: MyDraft-1B-4bit
      quant: Q4_0
```

Keys may also be `"target|host"` strings; values are `{draft, quant}` or
`[draft, quant]`.

## Feature flags

| Gate | Default | Effect |
|------|---------|--------|
| `strategies.draft_registry.enabled` | `false` | Reversible off |
| `NSA_DRAFT_REGISTRY_AUTO` | `1` in `.env.example`; code default follows strategy | Auto resolve |
| `NSA_DRAFT_MODEL_PATH` | empty | Force draft id/path |
| `NSA_DRAFT_QUANT` | `Q4_0` | Quant when path override set |

See ADR [`0014-ngram-cache-draft-registry.md`](../dipa/adr/0014-ngram-cache-draft-registry.md).
