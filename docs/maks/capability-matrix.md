"""Backend KV capability matrix (Axion-honest).

Cross-model reuse is NEVER assumed. MAKS adapts via CapabilityRegistry.
"""

# Capability Matrix

| Backend | prefix | shared | paged | speculative | cross-session | cross-model |
|---------|--------|--------|-------|-------------|---------------|-------------|
| opaque | Y | Y | N | N | Y | **N** |
| llama.cpp | Y | Y (MAKS pages) | N | partial | Y | **N** |
| SGLang | Y (radix) | Y (metadata) | Y | Y | Y | **N** |
| vLLM | Y (APC) | Y | Y | Y | Y | **N** |
| TGI | Y | N | N | N | Y | **N** |
| TensorRT-LLM | stub | stub | stub | stub | stub | **N** |
| DeepSpeed | stub | stub | stub | stub | stub | **N** |

## Adaptation rules

1. `supports_paged_kv` → page-table bind mode
2. else `supports_prefix_reuse` → hash/prefix reuse only
3. else → opaque session blob
4. `supports_cross_model_reuse` must be True **and** `KVIdentity` compatible — otherwise never reuse

## Query

```python
maks.capability_matrix()
maks.capabilities.flags("llama.cpp")
maks.capabilities.prefer_mode("vllm")  # → "paged"
```

REST: `GET /maks/capabilities`
