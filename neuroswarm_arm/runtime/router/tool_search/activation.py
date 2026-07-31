"""Pure activation rule for Hermes tool_search bridge vs pass-through."""

from __future__ import annotations

from typing import Literal


def decide_mode(
    *,
    enabled: str,
    threshold_pct: float,
    context_length: int,
    deferred_schema_tokens: int,
    has_deferrable: bool,
) -> Literal["pass_through", "bridge"]:
    """Return pass_through or bridge per TOOL_SEARCH_CONTRACT §2.2."""
    mode = str(enabled or "auto").strip().lower()
    if mode == "off":
        return "pass_through"
    if mode == "on":
        return "bridge" if has_deferrable else "pass_through"
    # auto
    ctx = max(1, int(context_length or 1))
    share = float(deferred_schema_tokens) / float(ctx)
    if share >= (float(threshold_pct) / 100.0):
        return "bridge"
    return "pass_through"
