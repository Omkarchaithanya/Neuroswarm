# Performix Kleidi vs stock — Instruction Mix + live decode

Generated: 2026-07-20T07:59:35Z

**Method:** Sustained chat decode load during capture. `instruction_mix --param mode=both` on deployed `libggml-cpu` extracted from live Docker images (`--workload` + `--working-dir`). Dynamic PMU rows were empty on this host (SPE empty); SIMD numbers are **static analysis of the live Kleidi vs stock CPU libs** captured during decode — not the old `02` snapshot.

| Capture | Artifact | SIMD summary |
|---|---|---|
| KleidiAI `libggml-cpu.so` | `03-instruction_mix_dynamic_kleidi.json` | **NEON 3.41% + SVE 0.94%** |
| Stock `libggml-cpu-armv9.2_2.so` | `04-instruction_mix_dynamic_baseline.json` | **NEON 2.14% + SVE 1.19%** |

Delta (Advanced SIMD / NEON): Kleidi **3.41%** vs stock **2.14%** (~+59% relative).

## Also captured (system-wide under load)

- `05-cpu_microarchitecture.json`
- `06-memory_access.json`
