"""ARM Memory Tagging Extension — unavailable on Axion; interface only."""

from __future__ import annotations

AVAILABLE = False


def tag_share(_ptr: int, _tag: int) -> None:
    raise NotImplementedError("ARM MTE unavailable on this platform")


def read_foreign(_ptr: int, _tag: int) -> bytes:
    raise NotImplementedError("ARM MTE unavailable on this platform")
