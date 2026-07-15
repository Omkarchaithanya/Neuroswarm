# Developer Guide — Inference

## Layout

- `neuroswarm_arm/armora/` — DX facade
- `neuroswarm_arm/runtime/dipa/control/` — managers
- `neuroswarm_arm/runtime/dipa/backends/` — HAL plugins
- `build/detect_cpu.py` / `build/generate_cmake.py` — KleidiAI CMake
- `docker/Dockerfile.llama-kleidiai` — production server image

## Add a backend

1. Implement `InferenceBackend` (health/prefill/decode/generate/cancel).
2. Set honest `BackendCapabilities` (never fake prefill-decode split).
3. `registry.register(YourBackend(...))` — zero kernel changes.

## Local mock

```bash
python -c "from neuroswarm_arm.runtime.dipa import build_dipa; r=build_dipa(use_mock=True); print(r.engine.generate([{'role':'user','content':'hi'}])); r.shutdown()"
```

## Tests

```bash
pytest tests/runtime/dipa/test_control_plane.py tests/runtime/dipa/test_inference_stress.py -q
```
