# Symbolization note (post RelWithDebInfo rebuild)

`libggml-cpu.so` in `nexus-arm/llama-kleidiai:server` was rebuilt with `RelWithDebInfo`, `-fno-omit-frame-pointer`, and is **with debug_info, not stripped**.

PID-scoped `code_hotspots` under chat load (single Compose stack) ranked `<Unknown code in libggml-cpu.so…>` ~79% — Arm Performix on this host did not resolve DWARF names for the container-mapped `.so`. The hotspot is still correctly attributed to Kleidi `libggml-cpu` (not idle/`default_idle_call`, not k3s/containerd).
