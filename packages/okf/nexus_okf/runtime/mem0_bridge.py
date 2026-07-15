from __future__ import annotations

from typing import Any

from nexus_okf.runtime.context import estimate_tokens
from nexus_okf.runtime.query import OKFContext


def merge_mem0_okf(
    facts: list[str],
    knowledge: OKFContext,
    tool_docs: OKFContext | None = None,
    *,
    max_tokens: int = 2000,
) -> str:
    """Strict separation: facts from Mem0, knowledge/docs from nexus_okf."""
    blocks: list[str] = []
    used = 0
    if facts:
        fact_block = "## Recent Facts (Mem0)\n" + "\n".join(f"- {f}" for f in facts)
        tok = estimate_tokens(fact_block)
        if used + tok <= max_tokens:
            blocks.append(fact_block)
            used += tok
    if knowledge and knowledge.text:
        k = "## Institutional Knowledge (OKF)\n" + knowledge.text
        tok = estimate_tokens(k)
        if used + tok <= max_tokens:
            blocks.append(k)
            used += tok
        else:
            # trim
            remain = max_tokens - used
            words = k.split()[:remain]
            blocks.append(" ".join(words))
            used = max_tokens
    if tool_docs and tool_docs.text and used < max_tokens:
        t = "## Tool Documentation (OKF)\n" + tool_docs.text
        tok = estimate_tokens(t)
        if used + tok <= max_tokens:
            blocks.append(t)
        else:
            words = t.split()[: max(0, max_tokens - used)]
            if words:
                blocks.append(" ".join(words))
    return "\n\n".join(blocks)
