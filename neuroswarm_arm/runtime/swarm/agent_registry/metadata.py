"""Metadata helpers for labels, tags, and ownership."""

from __future__ import annotations

from typing import Any, Mapping


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        key = str(t).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def normalize_labels(labels: Mapping[str, str] | None) -> dict[str, str]:
    if not labels:
        return {}
    return {str(k).strip(): str(v) for k, v in labels.items() if str(k).strip()}


def merge_metadata(
    base: Mapping[str, Any] | None,
    overlay: Mapping[str, Any] | None,
) -> dict[str, Any]:
    out = dict(base or {})
    for k, v in (overlay or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, Mapping):
            out[k] = merge_metadata(out[k], v)
        else:
            out[k] = v
    return out


def has_all_tags(agent_tags: list[str], required: list[str]) -> bool:
    if not required:
        return True
    have = set(normalize_tags(agent_tags))
    return all(t in have for t in normalize_tags(required))


def has_any_tag(agent_tags: list[str], candidates: list[str]) -> bool:
    if not candidates:
        return True
    have = set(normalize_tags(agent_tags))
    return any(t in have for t in normalize_tags(candidates))
