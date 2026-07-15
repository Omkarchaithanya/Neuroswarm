from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus_okf.compiler.ast import DocumentNode
from nexus_okf.internal.mmap_json import dump_json


def generate_indexes(
    artifact_dir: Path,
    docs: list[DocumentNode],
    graph: dict[str, Any],
    alias_map: dict[str, str],
) -> dict[str, Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    document_index = {
        d.id: {
            "path": d.rel_path,
            "type": d.doc_type,
            "title": d.title,
            "checksum": d.checksum,
            "priority": d.frontmatter.get("priority", 50),
            "tags": list(d.frontmatter.get("tags") or []),
            "visibility": d.frontmatter.get("visibility", "internal"),
            "owners": list(d.frontmatter.get("owners") or []),
            "namespace": d.frontmatter.get("namespace"),
            "token_budget": d.frontmatter.get("token_budget"),
            "mount": d.frontmatter.get("mount") or {},
            "description": d.frontmatter.get("description") or "",
            "status": d.frontmatter.get("status", "approved"),
            "timestamp": d.frontmatter.get("timestamp"),
            "recency_weight": d.frontmatter.get("recency_weight", 1.0),
        }
        for d in docs
    }
    out["document_index"] = _w(artifact_dir, "document_index.json", document_index)

    section_index = {
        d.id: [
            {
                "id": s.id,
                "title": s.title,
                "level": s.level,
                "tokens": s.token_estimate,
                "text": s.text,
            }
            for s in d.sections
        ]
        for d in docs
    }
    out["section_index"] = _w(artifact_dir, "section_index.json", section_index)

    inbound: dict[str, list[str]] = {}
    outbound: dict[str, list[str]] = {}
    for e in graph.get("edges") or []:
        outbound.setdefault(e["src"], []).append(e["dst"])
        inbound.setdefault(e["dst"], []).append(e["src"])
    out["reference_index"] = _w(
        artifact_dir, "reference_index.json", {"inbound": inbound, "outbound": outbound}
    )
    out["alias_map"] = _w(artifact_dir, "alias_map.json", alias_map)

    keyword_index: dict[str, list[str]] = {}
    for d in docs:
        words: set[str] = set()
        for t in list(d.frontmatter.get("tags") or []) + d.title.lower().split():
            words.add(str(t).lower())
        for w in d.body.lower().split():
            if len(w) > 3 and w.isalpha():
                words.add(w)
        for w in words:
            keyword_index.setdefault(w, []).append(d.id)
    out["keyword_index"] = _w(artifact_dir, "keyword_index.json", keyword_index)

    navigation_index: dict[str, Any] = {}
    for d in docs:
        if d.path.name == "index.md":
            parent = Path(d.rel_path).parent
            children = [x.id for x in docs if Path(x.rel_path).parent == parent and x.id != d.id]
            navigation_index[d.rel_path] = {"id": d.id, "children": children}
    out["navigation_index"] = _w(artifact_dir, "navigation_index.json", navigation_index)

    toc_index = {
        d.id: [{"id": s.id, "title": s.title, "level": s.level} for s in d.sections] for d in docs
    }
    out["toc_index"] = _w(artifact_dir, "toc_index.json", toc_index)
    metadata_index = {
        d.id: {k: v for k, v in d.frontmatter.items() if k not in {"ontology"}} for d in docs
    }
    out["metadata_index"] = _w(artifact_dir, "metadata_index.json", metadata_index)
    summary_index = {
        d.id: {
            "title": d.title,
            "description": d.frontmatter.get("description")
            or (d.body.strip().split("\n\n")[0][:400] if d.body.strip() else ""),
        }
        for d in docs
    }
    out["summary_index"] = _w(artifact_dir, "summary_index.json", summary_index)
    dep = {
        "nodes": [d.id for d in docs],
        "edges": [
            {"from": e["src"], "to": e["dst"]}
            for e in graph.get("edges") or []
            if e.get("pred")
            in {"depends_on", "extends", "see_also", "uses_tool", "governed_by", "contains"}
        ],
    }
    out["dependency_graph"] = _w(artifact_dir, "dependency_graph.json", dep)

    mount_index: dict[str, list[str]] = {}
    for d in docs:
        mount = d.frontmatter.get("mount") or {}
        for agent in mount.get("agents") or []:
            mount_index.setdefault(str(agent), []).append(d.id)
        for domain in mount.get("domains") or []:
            mount_index.setdefault(f"domain:{domain}", []).append(d.id)
    profile_dirs = {
        "research": "domains/research",
        "planner": "domains/planning",
        "coding": "domains/coding",
        "reviewer": "domains/review",
        "architect": "domains/architecture",
    }
    for profile, prefix in profile_dirs.items():
        for d in docs:
            if d.rel_path.startswith(prefix) or d.rel_path.startswith("policies/"):
                mount_index.setdefault(profile, [])
                if d.id not in mount_index[profile]:
                    mount_index[profile].append(d.id)
    out["mount_index"] = _w(artifact_dir, "mount_index.json", mount_index)
    return out


def _w(artifact_dir: Path, name: str, obj: Any) -> Path:
    path = artifact_dir / name
    dump_json(path, obj)
    return path
