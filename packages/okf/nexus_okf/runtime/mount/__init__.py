from __future__ import annotations

from typing import Any

DEFAULT_MOUNTS = {
    "research": ["domains/research", "tools/", "policies/"],
    "planner": ["domains/planning", "policies/", "playbooks/", "metrics/"],
    "coding": ["domains/coding", "tools/", "playbooks/"],
    "reviewer": ["domains/review", "policies/", "playbooks/"],
    "architect": ["domains/architecture", "policies/", "agents/", "ontology/", "playbooks/"],
}


class MountSession:
    def __init__(self, profile: str, allowed: set[str]):
        self.profile = profile
        self.allowed = allowed


class MountResolver:
    def __init__(self, loader: Any):
        self.loader = loader

    def allowed_ids(self, agent_profile: str, domains: list[str] | None = None) -> set[str]:
        mount_index = self.loader.mount_index
        ids: set[str] = set(mount_index.get(agent_profile) or [])
        if domains:
            for d in domains:
                ids.update(mount_index.get(f"domain:{d}") or [])
        prefixes = list(DEFAULT_MOUNTS.get(agent_profile, []))
        if domains:
            prefixes.extend(f"domains/{d}" for d in domains)
        for doc_id, meta in self.loader.document_index.items():
            path = str(meta.get("path") or "")
            if any(path.startswith(p) for p in prefixes):
                ids.add(doc_id)
            if path == "index.md":
                ids.add(doc_id)
        return ids

    def mount(self, agent_profile: str, domains: list[str] | None = None) -> MountSession:
        return MountSession(agent_profile, self.allowed_ids(agent_profile, domains))
