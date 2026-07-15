# MAKS (package docs)

Global KV **Memory Operating System** (NEXUS Layer 5).

Doc index:

- [Architecture](../../../docs/maks/architecture.md)
- [Memory OS](../../../docs/maks/memory-os.md)
- [Capability matrix](../../../docs/maks/capability-matrix.md)
- [Axion compatibility](../../../docs/maks/axion-compatibility.md)
- [MTE/CXL extension](../../../docs/maks/extension-mte-cxl.md)
- [Diagrams](../../../docs/maks/diagrams.md)
- [Roadmap](../../../docs/maks/roadmap.md)

## Quick test

```bash
pytest tests/runtime/maks -q
python -m neuroswarm_arm.runtime.maks.benchmarks
```
