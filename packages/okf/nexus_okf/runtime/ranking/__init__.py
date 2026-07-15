from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nexus_okf.runtime.ranking.features import feature_vector


class RankingEngine:
    def __init__(self, loader: Any, weights: dict[str, float] | None = None):
        self.loader = loader
        if weights is None:
            path = Path(__file__).with_name("weights.yaml")
            weights = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.weights = {str(k): float(v) for k, v in (weights or {}).items()}

    def score(
        self,
        doc_ids: list[str],
        *,
        query_tags: set[str],
        distances: dict[str, float],
        mount_ids: set[str],
        history: dict[str, float] | None = None,
    ) -> list[tuple[str, float]]:
        history = history or {}
        inbound = (self.loader.reference_index.get("inbound") or {})
        scored: list[tuple[str, float]] = []
        for doc_id in doc_ids:
            meta = self.loader.document_index.get(doc_id) or {}
            feats = feature_vector(
                doc_id,
                meta=meta,
                query_tags=query_tags,
                graph_dist=float(distances.get(doc_id, 3.0)),
                in_degree=len(inbound.get(doc_id) or []),
                mount_fit=1.0 if doc_id in mount_ids else 0.2,
                history_boost=float(history.get(doc_id, 0.0)),
            )
            total = sum(self.weights.get(k, 0.0) * v for k, v in feats.items())
            scored.append((doc_id, total))
        scored.sort(key=lambda x: -x[1])
        return scored
