# Inference API

## ARMORA (public)

```python
from neuroswarm_arm.armora import build_armora
from neuroswarm_arm.runtime.dipa import build_dipa

dipa = build_dipa(use_mock=True)  # or tier_urls={...}
armora = build_armora(dipa.engine)

handle = armora.load_model("tier1")
result = armora.generate([{"role": "user", "content": "hello"}])
for chunk in armora.stream([{"role": "user", "content": "hi"}]):
    print(chunk["text"], end="")
armora.warmup()
print(armora.metrics())
print(armora.health())
armora.shutdown()
```

Frozen methods: `load_model`, `generate`, `stream`, `warmup`, `metrics`, `health`, `shutdown`.

No llama.cpp URLs, GGUF paths, or GGML types in the public contract (opaque `ModelRef` / handles only).

## DIPA kernel

- `build_dipa(...)` → `DIPARuntime`
- `runtime.engine` → `IInferenceEngine`
- `runtime.handle(chat_request)` → HAOE / gateway chat path
- Backends via `InferenceBackend` + `BackendRegistry`
