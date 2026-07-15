"""Ordered fallback targets derived from ``ExecutionPlan.fallbacks``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from ..interfaces.types import ExecutionPlan


class FallbackKind(str, Enum):
    BACKEND = "backend"
    MODEL = "model"
    QUANT = "quant"


@dataclass(slots=True, frozen=True)
class FallbackTarget:
    """One recovery target: alternate backend, model, or quant."""

    kind: FallbackKind
    value: str
    raw: str = ""


def parse_fallback(entry: str) -> FallbackTarget:
    """Parse a fallback descriptor.

    Accepted forms
    --------------
    - ``backend:<name>`` / ``model:<name>`` / ``quant:<name>``
    - bare name → treated as backend
    """
    text = str(entry).strip()
    if not text:
        raise ValueError("empty fallback entry")
    if ":" in text:
        kind_s, _, value = text.partition(":")
        kind_s = kind_s.strip().lower()
        value = value.strip()
        if kind_s in {"backend", "model", "quant"} and value:
            return FallbackTarget(kind=FallbackKind(kind_s), value=value, raw=text)
    return FallbackTarget(kind=FallbackKind.BACKEND, value=text, raw=text)


@dataclass
class FallbackManager:
    """Iterate plan fallbacks for backend / model / quant recovery."""

    def targets(self, plan: ExecutionPlan | None) -> list[FallbackTarget]:
        if plan is None:
            return []
        out: list[FallbackTarget] = []
        for entry in plan.fallbacks:
            try:
                out.append(parse_fallback(entry))
            except ValueError:
                continue
        return out

    def next(
        self,
        plan: ExecutionPlan | None,
        *,
        cursor: int = 0,
        kind: FallbackKind | None = None,
    ) -> FallbackTarget | None:
        """Return the next fallback at *cursor*, optionally filtered by *kind*."""
        items = self.targets(plan)
        if kind is not None:
            items = [t for t in items if t.kind == kind]
        if cursor < 0 or cursor >= len(items):
            return None
        return items[cursor]

    def iter_backends(self, plan: ExecutionPlan | None) -> Iterator[str]:
        for target in self.targets(plan):
            if target.kind == FallbackKind.BACKEND:
                yield target.value

    def next_backend(self, plan: ExecutionPlan | None, *, cursor: int = 0) -> str | None:
        target = self.next(plan, cursor=cursor, kind=FallbackKind.BACKEND)
        return None if target is None else target.value

    def next_model(self, plan: ExecutionPlan | None, *, cursor: int = 0) -> str | None:
        target = self.next(plan, cursor=cursor, kind=FallbackKind.MODEL)
        return None if target is None else target.value

    def next_quant(self, plan: ExecutionPlan | None, *, cursor: int = 0) -> str | None:
        target = self.next(plan, cursor=cursor, kind=FallbackKind.QUANT)
        return None if target is None else target.value
