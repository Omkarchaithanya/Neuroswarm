"""O(1) n-gram continuation cache for prompt-lookup drafting."""

from __future__ import annotations

import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(slots=True)
class NgramTable:
    """Internal (n-1)-gram → next-token list table."""

    n: int
    max_entries: int
    entries: OrderedDict[tuple[str, ...], list[str]] = field(
        default_factory=OrderedDict
    )


class NgramCache:
    """Sliding-window (n-1)-gram → next_token[] map.

    Built lazily by proposers; rebuild on context_shift. Lookup is O(1)
    dict get; ``add`` is O(T) over tokens in the text.
    """

    def __init__(self, n: int = 3, max_entries: int = 1_000_000) -> None:
        self._table = NgramTable(
            n=max(2, int(n)),
            max_entries=max(1, int(max_entries)),
        )

    @property
    def n(self) -> int:
        return self._table.n

    @property
    def max_entries(self) -> int:
        return self._table.max_entries

    def clear(self) -> None:
        self._table.entries.clear()

    def add(self, text: str) -> None:
        tokens = text.split() if text else []
        n = self._table.n
        if len(tokens) < n:
            return
        entries = self._table.entries
        max_e = self._table.max_entries
        for i in range(len(tokens) - n + 1):
            key = tuple(tokens[i : i + n - 1])
            nxt = tokens[i + n - 1]
            if key in entries:
                entries[key].append(nxt)
                entries.move_to_end(key)
            else:
                if len(entries) >= max_e:
                    entries.popitem(last=False)
                entries[key] = [nxt]

    def lookup(self, seed_tokens: Iterable[str]) -> list[str] | None:
        seed = tuple(seed_tokens)
        if len(seed) != self._table.n - 1:
            return None
        found = self._table.entries.get(seed)
        if not found:
            return None
        return list(found)

    def __len__(self) -> int:
        return len(self._table.entries)

    def __sizeof__(self) -> int:
        # Do not call sys.getsizeof(self) — that re-enters __sizeof__.
        size = object.__sizeof__(self) + object.__sizeof__(self._table)
        size += sys.getsizeof(self._table.entries)
        for key, vals in self._table.entries.items():
            size += sys.getsizeof(key)
            for part in key:
                size += sys.getsizeof(part)
            size += sys.getsizeof(vals)
            for v in vals:
                size += sys.getsizeof(v)
        return size
