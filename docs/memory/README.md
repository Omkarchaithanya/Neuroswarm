# Cognitive Memory Runtime

See [architecture.md](architecture.md), [MEM0_OFFICIAL_GAP_ANALYSIS.md](MEM0_OFFICIAL_GAP_ANALYSIS.md), [MEM0_MODULE_MAPPING.md](MEM0_MODULE_MAPPING.md).

Quick start:

```python
from neuroswarm_arm.runtime.memory import build_memory_runtime, Mem0Adapter

mem = build_memory_runtime("work/memory")  # Mem0 primary; JSON emergency only
mem.remember([{"role": "user", "content": "I prefer Arm CPUs"}], owner="alice")
print(mem.recall("alice", "Arm"))
```
