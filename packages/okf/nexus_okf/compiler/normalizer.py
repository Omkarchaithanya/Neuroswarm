# Origin: NEXUS Extension
"""NEXUS normalizer — does not invent official ``type``; keeps Concept ID = path."""

from __future__ import annotations

from nexus_okf.compiler.ast import DocumentNode


def normalize_document(doc: DocumentNode) -> DocumentNode:
    fm = dict(doc.frontmatter)
    # Do NOT setdefault type from empty — missing type stays missing for validators
    if doc.doc_type:
        fm.setdefault("type", doc.doc_type)
    fm.setdefault("title", doc.title)
    fm.setdefault("visibility", "internal")
    fm.setdefault("status", "approved")
    fm.setdefault("priority", 50)
    fm.setdefault("tags", [])
    fm.setdefault("aliases", [])
    # Official Concept ID remains doc.id (path). FM id is NEXUS alias only.
    fm.setdefault("concept_id", doc.id)
    doc.frontmatter = fm
    if fm.get("type"):
        doc.doc_type = str(fm["type"])
    doc.title = str(fm.get("title") or doc.title)
    # Never replace doc.id with fm["id"] — official Concept ID is path-based
    seen: set[str] = set()
    for sec in doc.sections:
        base = sec.id
        n = 1
        while sec.id in seen:
            n += 1
            sec.id = f"{base}-{n}"
        seen.add(sec.id)
    return doc
