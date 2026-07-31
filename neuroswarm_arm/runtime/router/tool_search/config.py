"""Hermes tool_search config — TOOL_SEARCH_* env keys only."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True, frozen=True)
class ToolSearchConfig:
    enabled: Literal["auto", "on", "off"] = "auto"
    threshold_pct: float = 10.0
    search_default_limit: int = 5
    max_search_limit: int = 20
    listing: Literal["auto", "on", "off"] = "auto"
    listing_max_tokens: int = 20000

    def __post_init__(self) -> None:
        if not (0.0 <= float(self.threshold_pct) <= 100.0):
            raise ValueError("threshold_pct must be in [0, 100]")
        if not (1 <= int(self.search_default_limit) <= int(self.max_search_limit) <= 50):
            raise ValueError("require 1 <= search_default_limit <= max_search_limit <= 50")
        if int(self.listing_max_tokens) < 0:
            raise ValueError("listing_max_tokens must be >= 0")
        if self.enabled not in {"auto", "on", "off"}:
            raise ValueError("enabled must be auto|on|off")
        if self.listing not in {"auto", "on", "off"}:
            raise ValueError("listing must be auto|on|off")

    @classmethod
    def from_env(cls) -> ToolSearchConfig:
        enabled = str(os.getenv("TOOL_SEARCH_ENABLED", "auto") or "auto").strip().lower()
        if enabled not in {"auto", "on", "off"}:
            enabled = "auto"
        listing = str(os.getenv("TOOL_SEARCH_LISTING", "auto") or "auto").strip().lower()
        if listing not in {"auto", "on", "off"}:
            listing = "auto"
        return cls(
            enabled=enabled,  # type: ignore[arg-type]
            threshold_pct=float(os.getenv("TOOL_SEARCH_THRESHOLD_PCT", "10") or 10),
            search_default_limit=int(os.getenv("TOOL_SEARCH_DEFAULT_LIMIT", "5") or 5),
            max_search_limit=int(os.getenv("TOOL_SEARCH_MAX_LIMIT", "20") or 20),
            listing=listing,  # type: ignore[arg-type]
            listing_max_tokens=int(os.getenv("TOOL_SEARCH_LISTING_MAX_TOKENS", "20000") or 20000),
        )
