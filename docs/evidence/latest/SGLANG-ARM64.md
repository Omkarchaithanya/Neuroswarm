# SGLang arm64 verify

Date: 2026-07-18 (Axion)

```text
Inspecting lmsysorg/sglang:latest
PASS: arm64 present in manifest for lmsysorg/sglang:latest
Cite: Arm May 2026 Neoverse SGLang blog + SGLANG_USE_CPU_ENGINE=1
```

Command: `bash scripts/verify-sglang-arm64.sh`

Manifest includes `linux/arm64` alongside `linux/amd64`. Safe to claim optional Compose profile `pd` with `SGLANG_USE_CPU_ENGINE=1` when that profile is enabled.
