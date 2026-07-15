"""Acceptance gate for cascade tier outputs."""

from __future__ import annotations

from typing import Any, Mapping

from .verifier import Verifier, confidence


def accepts(
    text: str,
    threshold: float,
    cfg: Mapping[str, Any] | None = None,
) -> bool:
    """Return ``True`` when confidence(*text*) meets *threshold*."""
    return confidence(text, cfg) >= float(threshold)


class CascadeValidator:
    """Thresholded acceptance using a shared :class:`Verifier`."""

    def __init__(
        self,
        verifier: Verifier | None = None,
        *,
        cfg: Mapping[str, Any] | None = None,
    ) -> None:
        self.verifier = verifier or Verifier(cfg)

    def accepts(self, text: str, threshold: float) -> bool:
        return self.verifier.score(text) >= float(threshold)
