"""Graph visualization helpers — Mermaid, Graphviz DOT, ASCII, JSON Graph."""

from __future__ import annotations

import json
from typing import Any

from .enums import EdgeKind
from .graph import TaskGraph


def to_mermaid(graph: TaskGraph) -> str:
    lines = ["flowchart TD"]
    for nid, node in graph.nodes.items():
        label = node.display_name or node.name or nid
        safe = _mermaid_id(nid)
        lines.append(f'  {safe}["{label}"]')
    for edge in graph.edges:
        src = _mermaid_id(edge.src)
        dst = _mermaid_id(edge.dst)
        arrow = "-->" if edge.kind is EdgeKind.HARD else "-.->"
        if edge.label:
            lines.append(f"  {src} {arrow}|{edge.label}| {dst}")
        else:
            lines.append(f"  {src} {arrow} {dst}")
    return "\n".join(lines)


def to_dot(graph: TaskGraph) -> str:
    lines = [f'digraph "{graph.name or graph.graph_id}" {{']
    for nid, node in graph.nodes.items():
        label = node.display_name or node.name or nid
        lines.append(f'  "{nid}" [label="{label}"];')
    for edge in graph.edges:
        style = "solid" if edge.kind is EdgeKind.HARD else "dashed"
        lbl = f' label="{edge.label}"' if edge.label else ""
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [style={style}{lbl}];')
    lines.append("}")
    return "\n".join(lines)


def to_ascii(graph: TaskGraph) -> str:
    """Simple layered ASCII tree."""
    try:
        layers = graph.execution_layers()
    except Exception:  # noqa: BLE001
        layers = [[nid] for nid in graph.nodes]
    rows: list[str] = []
    for i, layer in enumerate(layers):
        names = []
        for nid in layer:
            node = graph.nodes[nid]
            names.append(node.name or nid[:8])
        rows.append(f"L{i}: " + " | ".join(names))
        if i < len(layers) - 1:
            rows.append("     |")
            rows.append("     v")
    return "\n".join(rows)


def to_json_graph(graph: TaskGraph) -> dict[str, Any]:
    """JSON Graph format-ish structure for tooling."""
    return {
        "graph": {
            "id": graph.graph_id,
            "label": graph.name,
            "metadata": graph.metadata,
        },
        "nodes": [
            {
                "id": nid,
                "label": node.display_name or node.name or nid,
                "metadata": {
                    "node_type": node.node_type.value,
                    "priority": int(node.priority),
                    "status": node.status.value,
                    **node.metadata,
                },
            }
            for nid, node in graph.nodes.items()
        ],
        "edges": [
            {
                "source": e.src,
                "target": e.dst,
                "relation": e.kind.value,
                "label": e.label,
                "metadata": e.metadata,
            }
            for e in graph.edges
        ],
    }


def to_json_graph_str(graph: TaskGraph, *, indent: int = 2) -> str:
    return json.dumps(to_json_graph(graph), indent=indent)


def _mermaid_id(nid: str) -> str:
    return "n_" + "".join(ch if ch.isalnum() else "_" for ch in nid)
