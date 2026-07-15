"""Cancellation tokens — cooperative cancel across workflow nodes."""

from __future__ import annotations

from threading import Event
from typing import Callable


class CancellationToken:
    def __init__(self, parent: CancellationToken | None = None) -> None:
        self._event = Event()
        self._parent = parent
        self._callbacks: list[Callable[[], None]] = []

    def cancel(self) -> None:
        if self._event.is_set():
            return
        self._event.set()
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                continue
        if self._parent is not None:
            # Child cancel does not cancel parent.
            pass

    def is_cancelled(self) -> bool:
        if self._event.is_set():
            return True
        if self._parent is not None and self._parent.is_cancelled():
            return True
        return False

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise CancelledError("operation cancelled")

    def on_cancel(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)
        if self.is_cancelled():
            try:
                callback()
            except Exception:
                pass

    def child(self) -> CancellationToken:
        return CancellationToken(parent=self)

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


class CancelledError(RuntimeError):
    pass


class CancellationManager:
    """Tracks tokens by workflow / task id."""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}

    def create(self, key: str, parent: CancellationToken | None = None) -> CancellationToken:
        token = CancellationToken(parent=parent)
        self._tokens[key] = token
        return token

    def get(self, key: str) -> CancellationToken | None:
        return self._tokens.get(key)

    def cancel(self, key: str) -> bool:
        token = self._tokens.get(key)
        if token is None:
            return False
        token.cancel()
        return True

    def discard(self, key: str) -> None:
        self._tokens.pop(key, None)
