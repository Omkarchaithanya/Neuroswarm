from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus_okf.runtime.cache_manager import CacheManager
from nexus_okf.runtime.loader import ArtifactLoader
from nexus_okf.runtime.mount import MountResolver, MountSession
from nexus_okf.runtime.navigator import Navigator, NavNode
from nexus_okf.runtime.query import OKFContext, OKFQuery, QueryPipeline
from nexus_okf.runtime.telemetry import OKFMetrics


class OKFRuntime:
    def __init__(self, artifact_dir: Path, source_root: Path | None = None):
        self.artifact_dir = Path(artifact_dir)
        self.source_root = Path(source_root) if source_root else self.artifact_dir.parent.parent
        self.loader = ArtifactLoader(self.artifact_dir)
        self.loader.load()
        self.cache = CacheManager()
        self.mounts = MountResolver(self.loader)
        self.navigator = Navigator(self.loader)
        self.pipeline = QueryPipeline(self.loader, self.cache, self.mounts)
        self.metrics = OKFMetrics()

    def query(self, req: OKFQuery, history: dict[str, float] | None = None) -> OKFContext:
        ctx = self.pipeline.run(req, history=history)
        self.metrics.record_query(ctx)
        return ctx

    def navigate(self, path_or_id: str, depth: int = 1) -> NavNode:
        return self.navigator.navigate(path_or_id, depth=depth)

    def mount(self, agent_profile: str, domains: list[str] | None = None) -> MountSession:
        return self.mounts.mount(agent_profile, domains)

    def load_tool_docs(self, tool_ids: list[str], budget: int = 800) -> OKFContext:
        """Load tool documentation AFTER MCP routing — never before."""
        allowed = set()
        for doc_id, meta in self.loader.document_index.items():
            if meta.get("type") == "tool":
                path = str(meta.get("path") or "")
                title = str(meta.get("title") or "").lower()
                for tid in tool_ids:
                    t = tid.lower()
                    if t in doc_id.lower() or t in path.lower() or t in title:
                        allowed.add(doc_id)
        # also match by resource / id equality
        for tid in tool_ids:
            if tid in self.loader.document_index:
                allowed.add(tid)
            alias = self.loader.alias_map.get(tid)
            if alias:
                allowed.add(alias)
        req = OKFQuery(
            text=" ".join(tool_ids) + " tool documentation",
            agent_profile="coding",
            token_budget=budget,
            include_types=["tool"],
        )
        # temporarily restrict via domains None and filter ranked later
        ctx = self.query(req)
        if allowed:
            ctx.sections = [s for s in ctx.sections if s.id in allowed]
            ctx.provenance = [s.path for s in ctx.sections]
            ctx.tokens_used = sum(s.tokens for s in ctx.sections)
            ctx.text = self.pipeline.context.stitch(ctx.sections)
        return ctx

    def validate_bundle(self) -> dict[str, Any]:
        from nexus_okf.internal.mmap_json import load_json

        diag = self.artifact_dir / "diagnostics.json"
        if diag.exists():
            return load_json(diag)
        return {"ok": False, "errors": 1, "items": [{"code": "NO_DIAG", "message": "missing diagnostics"}]}

    # SupportsOKF protocol
    def load_index(self) -> Any:
        return self.navigate("index.md")

    def load_topic(self, relative_path: str) -> Any:
        return self.navigate(relative_path)


def build_runtime(artifact_dir: Path, source_root: Path | None = None) -> OKFRuntime:
    return OKFRuntime(artifact_dir=artifact_dir, source_root=source_root)
