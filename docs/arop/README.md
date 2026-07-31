# AROP docs

**Shipping now (v1):** rule-based Performix-driven knob tuner at [`neuroswarm_arm/arop/`](../../neuroswarm_arm/arop/) — dry-run default, fail-loud metrics, gateway-only apply. Not PPO, not GEPA, not GGUF re-quant, not CSS V3/MTE. See [architecture.md](architecture.md#arop-v1-cli-tuner-rule-based-shipping-now) and the module [README](../../neuroswarm_arm/arop/README.md).

**Scaffolding (later):** `neuroswarm_arm/evolution/` Plane 5 (`RuntimeOptimizer`, GEPA, PolicyRegistry canary) — docs below describe that broader design; do not treat it as the Axion-proven v1 path.

- [architecture.md](architecture.md)
- [diagrams.md](diagrams.md)
- [plugin-guide.md](plugin-guide.md)
- [gepa.md](gepa.md) — official Genetic-Pareto text evolution
- [gepa-gap-analysis.md](gepa-gap-analysis.md)
- ADRs under `adr/`
