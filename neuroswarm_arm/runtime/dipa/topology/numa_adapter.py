"""NUMA adapter — single-node fallback on Axion."""

from __future__ import annotations


class NumaAdapter:
    def nodes(self) -> list[int]:
        return [0]

    def preferred(self) -> int:
        return 0
