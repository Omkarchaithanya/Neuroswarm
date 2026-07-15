# ACR Architecture

## Pipeline (compiler metaphor)

```mermaid
flowchart LR
  Req[UserRequest] --> Und[UnderstandingEngine]
  Und --> CRG[ContextRequirementGraph]
  CRG --> Plan[ContextPlanner]
  Plan --> REP[RetrievalExecutionPlan]
  REP --> MemRT[MemoryRuntimeAdapter]
  REP --> KnowRT[KnowledgeRuntimeAdapter]
  MemRT --> Score[ScoringEngine]
  KnowRT --> Score
  Score --> Comp[CompressionEngine]
  Comp --> Asm[AssemblyEngine]
  Asm --> Snap[ContextSnapshot]
  Snap --> Cache[ContextCache]
  Snap --> Evo[EvolutionEngine]
  HW[HardwareTopology] -.-> Cache
  HW -.-> Comp
```

## Class diagram

```mermaid
classDiagram
  class AdaptiveContextRuntime {
    +build_context()
    +evolve()
    +health()
  }
  class UnderstandingEngine
  class ContextPlanner
  class MemoryRuntimeAdapter
  class KnowledgeRuntimeAdapter
  class ScoringEngine
  class CompressionEngine
  class AssemblyEngine
  class ContextCache
  class ContextVersioning
  class EvolutionEngine
  class HardwareTopology

  AdaptiveContextRuntime --> UnderstandingEngine
  AdaptiveContextRuntime --> ContextPlanner
  AdaptiveContextRuntime --> MemoryRuntimeAdapter
  AdaptiveContextRuntime --> KnowledgeRuntimeAdapter
  AdaptiveContextRuntime --> ScoringEngine
  AdaptiveContextRuntime --> CompressionEngine
  AdaptiveContextRuntime --> AssemblyEngine
  AdaptiveContextRuntime --> ContextCache
  AdaptiveContextRuntime --> ContextVersioning
  AdaptiveContextRuntime --> EvolutionEngine
  AdaptiveContextRuntime --> HardwareTopology
```

## Sequence (HAOE chat)

```mermaid
sequenceDiagram
  participant HAOE
  participant ACR
  participant Mem as NeuroMemory
  participant OKF
  participant DIPA
  HAOE->>ACR: build_context
  ACR->>Mem: retrieve plan steps
  ACR->>OKF: query + tool_docs
  ACR-->>HAOE: ContextSnapshot
  HAOE->>DIPA: tool_prompt_block
  HAOE->>ACR: evolve on complete
```

## Context lifecycle

```mermaid
stateDiagram-v2
  [*] --> Understood
  Understood --> Planned
  Planned --> Retrieved
  Retrieved --> Scored
  Scored --> Compressed
  Compressed --> Assembled
  Assembled --> Versioned
  Versioned --> Cached
  Cached --> Evolved
  Evolved --> [*]
```

## Separation

- ADR-0001: Context OS is not RAG
- ADR-0002: ACR wraps Mem0 + OKF; never merges storage
- ADR-0003: measurable compression, not fixed %
- ADR-0004: HardwareTopology HAL (NUMA if present else local)

## Package

`neuroswarm_arm/runtime/acr/` — see [developer.md](developer.md).
