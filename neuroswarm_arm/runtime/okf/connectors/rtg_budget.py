from __future__ import annotations

from typing import Any


def report_okf_budget(ctx_baggage: dict[str, Any]) -> int:
    """Projected OKF tokens for RTG envelope."""
    return int(ctx_baggage.get("okf_tokens") or 0)
