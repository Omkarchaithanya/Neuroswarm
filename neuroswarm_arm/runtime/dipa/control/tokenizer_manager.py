"""TokenizerManager — backend-delegated tokenization (no tokenizer ownership)."""

from __future__ import annotations

from typing import Any

from .backend_manager import BackendManager


class TokenizerManager:
    def __init__(self, backends: BackendManager) -> None:
        self.backends = backends

    def tokenize(self, text: str, *, backend: str | None = None) -> list[int]:
        be = self._pick(backend)
        fn = getattr(be, "tokenize", None) if be else None
        if callable(fn):
            return list(fn(text))
        # Approx fallback — never claim real token ids.
        return list(range(max(1, len(text.split()))))

    def detokenize(self, ids: list[int], *, backend: str | None = None) -> str:
        be = self._pick(backend)
        fn = getattr(be, "detokenize", None) if be else None
        if callable(fn):
            return str(fn(ids))
        return " ".join(f"<{i}>" for i in ids)

    def count(self, text: str, *, backend: str | None = None) -> int:
        return len(self.tokenize(text, backend=backend))

    def _pick(self, backend: str | None) -> Any | None:
        if backend:
            return self.backends.get(backend)
        names = self.backends.list()
        return self.backends.get(names[0]) if names else None
