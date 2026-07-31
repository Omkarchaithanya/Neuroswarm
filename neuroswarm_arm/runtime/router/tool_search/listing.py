"""Listing manifest for bridge mode — TOOL_SEARCH_CONTRACT §2.4 / §4.3."""

from __future__ import annotations

from typing import Any, Iterable

from ..tool_schema_builder import estimate_schema_tokens


def _server_of(tool: Any) -> str:
    server = getattr(tool, "server", None)
    if server:
        return str(server)
    ns = str(getattr(tool, "namespace", "") or "")
    if ns and ns != "default":
        return ns.split(".")[0].split("/")[0]
    tid = str(getattr(tool, "id", "") or "")
    if "." in tid:
        return tid.split(".", 1)[0]
    return ""


def _line_for(tool: Any) -> str:
    name = str(getattr(tool, "name", "") or getattr(tool, "id", "") or "tool")
    desc = str(getattr(tool, "description", "") or "").strip()
    if desc:
        return f"  - {name} — {desc}"
    return f"  - {name}"


def build_listing_manifest(registry: Any, max_tokens: int) -> tuple[str, bool]:
    """Build ``<tool_listing>`` block capped at ``max_tokens``.

    Returns ``(manifest, truncated)``. Truncation drops from the end and appends
    the mandatory footer.
    """
    tools: list[Any]
    if registry is None:
        tools = []
    elif hasattr(registry, "as_list"):
        tools = list(registry.as_list())
    elif isinstance(registry, Iterable) and not isinstance(registry, (str, bytes)):
        tools = list(registry)
    else:
        tools = []

    groups: dict[str, list[Any]] = {}
    order: list[str] = []
    for tool in tools:
        sid = _server_of(tool)
        if sid not in groups:
            groups[sid] = []
            order.append(sid)
        groups[sid].append(tool)

    lines: list[str] = ["<tool_listing>"]
    for sid in order:
        if sid:
            lines.append(f"server: {sid}")
        for tool in groups[sid]:
            lines.append(_line_for(tool))
    lines.append("</tool_listing>")

    budget = max(0, int(max_tokens))
    if budget == 0:
        footer = '... and 0 more tools; call tool_search(query="...") to drill in.'
        return f"<tool_listing>\n{footer}\n</tool_listing>", True

    def _tokens(text: str) -> int:
        return estimate_schema_tokens({"manifest": text})

    full = "\n".join(lines)
    if _tokens(full) <= budget:
        return full, False

    # Drop body lines from the end (keep open/close tags).
    body = lines[1:-1]
    dropped = 0
    while body:
        candidate_lines = ["<tool_listing>", *body, "</tool_listing>"]
        # Reserve room for footer once we know we must truncate.
        footer = f'... and {dropped + 1} more tools; call tool_search(query="...") to drill in.'
        trial = "\n".join([*candidate_lines[:-1], footer, candidate_lines[-1]])
        if _tokens(trial) <= budget:
            # Keep dropping until under budget with accurate remaining count.
            break
        body.pop()
        dropped += 1

    # Refine: after loop, body fits with dropped+? — recount remaining omitted.
    omitted = max(dropped, len(tools) - max(0, sum(1 for ln in body if ln.startswith("  - "))))
    # Prefer tool-line count for footer accuracy.
    kept_tools = sum(1 for ln in body if ln.startswith("  - "))
    omitted = max(0, len(tools) - kept_tools)
    footer = f'... and {omitted} more tools; call tool_search(query="...") to drill in.'
    while body:
        trial = "\n".join(["<tool_listing>", *body, footer, "</tool_listing>"])
        if _tokens(trial) <= budget:
            return trial, True
        # Still too big — drop another line and recompute omitted.
        body.pop()
        kept_tools = sum(1 for ln in body if ln.startswith("  - "))
        omitted = max(0, len(tools) - kept_tools)
        footer = f'... and {omitted} more tools; call tool_search(query="...") to drill in.'

    # Extreme: only tags + footer.
    footer = f'... and {len(tools)} more tools; call tool_search(query="...") to drill in.'
    return f"<tool_listing>\n{footer}\n</tool_listing>", True
