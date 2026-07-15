from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BudgetManager:
    soft: int
    hard: int

    def remaining(self, used: int) -> int:
        return max(0, self.soft - used)

    def allow(self, used: int, add: int) -> bool:
        return used + add <= self.hard

    def clip(self, used: int, add: int) -> int:
        return max(0, min(add, self.hard - used))
