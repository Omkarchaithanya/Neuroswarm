# Devpost Project Overview (paste-ready)

**Submit by Aug 13, 2026** (deadline Aug 14 16:00 PDT).

## Overview field

NeuroSwarm-Arm is a self-evolving, cost-optimized multi-agent AI runtime for Arm Neoverse. Three-tier CPU cascade on **KleidiAI** llama.cpp (`nexus-arm/llama-kleidiai:server`), semantic MCP router (6 templates indexed), reasoning-token governor, and Arm Performix closed-loop tuning with real **`code_hotspots`** + **`instruction_mix`** receipts (NEON/SVE groups visible). Live demo on **GCP Axion c4a-standard-8** (Neoverse-V2, 1 NUMA — Option A adaptive topology). Auto-detects NUMA/CXL/MTE and degrades safely on single-NUMA VMs; activates NUMA-split/CXL on multi-socket Neoverse. Helm + Compose + Grafana. Why it wins: evidence matches the pitch — not stock llama.cpp and not Graviton5 fantasy.

## Prize intent

- Primary: $1,000 Best in Cloud AI → $3,000 Overall Winner  
- Fallback: **$2,000 Overall Runner-Up**

## Judges (3)

Avin Zarlez · Michael Hall · Gabriel Peterson

## Links to include

- Source repo (public)  
- Demo video &lt;3 min (YouTube/Vimeo/Youku) showing **Axion** run  
- `docs/setup.md`, `docs/evidence/`, `docs/DEVPOST-OVERVIEW.md`
