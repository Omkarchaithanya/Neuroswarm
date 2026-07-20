---
okf_version: "1.0"
type: concept
id: nexus.architecture.aqr
title: AQR — Adaptive Quantization Router
description: Per-agent-role quantization policy; connector into DIPA planning
tags: [aqr, quantization, layer3]
resource: mcp://aqr
namespace: nexus.architecture
visibility: internal
status: approved
priority: 75
token_budget: 600
mount:
  agents: [architect, coding]
  domains: [architecture]
ontology:
  class: Concept
  relations:
    - {pred: depends_on, obj: nexus.architecture.dipa}
    - {pred: see_also, obj: nexus.architecture.arm_cascade}
timestamp: 2026-07-16T00:00:00Z
---

# AQR

Adaptive Quantization Router: chooses quant profiles (GGUF / INT4 / INT8 / hybrid) per agent role and hardware policy. DIPA asks AQR via connectors; AQR does not own backends.

## Package

- Code: `neuroswarm_arm.runtime.aqr`
- Config: `neuroswarm_arm/runtime/aqr/config/` (`policy.yaml`, `quants.yaml`, `scoring.yaml`, `cascade_profiles.yaml`, `discovery.yaml`)

## Responsibilities

- Map agent role → quant recipe
- Score candidates against hardware + cascade tier
- Expose policy metadata for AROP evolution write-back

## Integration

DIPA lifecycle step: **Quant(AQR)** after policy, before AWPP warm and MAKS KV.

## Notes

AQR is a **connector**, not an inference owner (DIPA ADR: connectors-not-ownership).
