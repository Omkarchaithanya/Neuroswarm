"""NUMA locality helpers — degrade to node 0 on single-socket Axion."""

from __future__ import annotations

import os

AVAILABLE = True  # soft — always "available" with node-0 fallback


def preferred_node() -> int:
    raw = os.getenv("NSA_MAKS_NUMA_NODE", "0")
    try:
        return int(raw)
    except ValueError:
        return 0


def affinity_cores() -> list[int]:
    raw = os.getenv("NSA_MAKS_AFFINITY", "")
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out
