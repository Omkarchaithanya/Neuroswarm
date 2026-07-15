from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nexus_okf.compiler.ast import DocumentNode
from nexus_okf.compiler.diagnostics import Diagnostics

TYPE_TO_CLASS = {
    "agent": "AgentRole",
    "tool": "Tool",
    "policy": "Policy",
    "playbook": "Playbook",
    "metric": "Metric",
    "domain": "Domain",
    "concept": "Concept",
    "ontology": "Concept",
    "index": "Concept",
}


def load_ontology(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        # packages/okf/ontology/nexus-core.yaml relative to this file
        path = Path(__file__).resolve().parents[2] / "ontology" / "nexus-core.yaml"
    if not path.exists():
        return {"classes": {}, "predicates": {}, "type_map": TYPE_TO_CLASS}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("type_map", TYPE_TO_CLASS)
    return data


def check_ontology(docs: list[DocumentNode], ontology: dict[str, Any], diag: Diagnostics) -> None:
    classes = ontology.get("classes") or {}
    predicates = ontology.get("predicates") or {}
    type_map = ontology.get("type_map") or TYPE_TO_CLASS

    for doc in docs:
        if doc.reserved and doc.path.name in {"index.md", "log.md"}:
            continue
        if "type" not in doc.frontmatter and not doc.reserved:
            diag.error("MISSING_TYPE", "Missing required frontmatter field: type", doc.rel_path)
            continue
        cls = type_map.get(doc.doc_type)
        if cls and cls not in classes and classes:
            diag.warning("UNKNOWN_CLASS", f"Type {doc.doc_type} maps to unknown class {cls}", doc.rel_path)
        ont = doc.frontmatter.get("ontology") or {}
        for rel in ont.get("relations") or []:
            pred = rel.get("pred")
            if pred and pred not in predicates and predicates:
                diag.warning("UNKNOWN_PRED", f"Unknown predicate {pred}", doc.rel_path)
        if doc.doc_type == "agent" and not doc.frontmatter.get("title"):
            diag.error("MISSING_META", "Agent documents require title", doc.rel_path)
