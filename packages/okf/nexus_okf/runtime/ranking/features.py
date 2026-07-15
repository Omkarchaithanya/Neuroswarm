from __future__ import annotations

from typing import Any


def feature_vector(
    doc_id: str,
    *,
    meta: dict[str, Any],
    query_tags: set[str],
    graph_dist: float,
    in_degree: int,
    mount_fit: float,
    history_boost: float = 0.0,
    ownership_match: float = 0.0,
) -> dict[str, float]:
    tags = set(str(t).lower() for t in (meta.get("tags") or []))
    overlap = (len(tags & query_tags) / max(1, len(query_tags))) if query_tags else 0.0
    priority = float(meta.get("priority") or 50) / 100.0
    return {
        "hierarchy": 1.0 / (1.0 + graph_dist),
        "priority": priority,
        "recency": float(meta.get("recency_weight") or 1.0) * 0.5,
        "ownership": ownership_match,
        "tag_overlap": overlap,
        "reference_score": min(1.0, in_degree / 10.0),
        "graph_distance": 1.0 / (1.0 + graph_dist),
        "ontology_distance": 1.0 / (1.0 + graph_dist),
        "manual_weight": priority,
        "agent_mount_fit": mount_fit,
        "user_history": history_boost,
    }
