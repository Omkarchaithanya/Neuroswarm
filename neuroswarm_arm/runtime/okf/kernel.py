from __future__ import annotations

from pathlib import Path
from typing import Any

from .factory import OKFConfig


class OKFNexusRuntime:
    """NEXUS facade over packages/okf Knowledge OS."""

    def __init__(self, config: OKFConfig, metrics_bridge: Any = None):
        self.config = config
        self.metrics_bridge = metrics_bridge
        self._runtime = None
        if config.enabled:
            self._ensure_runtime()

    def _ensure_runtime(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        from nexus_okf.compiler.pipeline import compile_bundle
        from nexus_okf.runtime.kernel import build_runtime

        art = self.config.artifact_root
        manifest = art / "knowledge_manifest.json"
        if self.config.auto_build and (not manifest.exists()):
            compile_bundle(self.config.source_root, art, strict=False)
        elif self.config.auto_build and not (art / "runtime_bundle.okfb").exists():
            compile_bundle(self.config.source_root, art, strict=False)
        self._runtime = build_runtime(art, self.config.source_root)
        return self._runtime

    @property
    def runtime(self) -> Any:
        return self._ensure_runtime()

    def query(self, text: str, agent_profile: str = "architect", token_budget: int | None = None) -> Any:
        from nexus_okf.runtime.query import OKFQuery

        return self.runtime.query(
            OKFQuery(
                text=text,
                agent_profile=agent_profile,
                token_budget=token_budget or self.config.token_budget,
            )
        )

    def load_tool_docs(self, tool_ids: list[str], budget: int = 800) -> Any:
        return self.runtime.load_tool_docs(tool_ids, budget=budget)

    def navigate(self, path_or_id: str, depth: int = 1) -> Any:
        return self.runtime.navigate(path_or_id, depth=depth)

    def load_index(self) -> Any:
        return self.runtime.load_index()

    def load_topic(self, relative_path: str) -> Any:
        return self.runtime.load_topic(relative_path)

    def status(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {"enabled": False}
        try:
            rt = self.runtime
            return {
                "enabled": True,
                "docs": len(rt.loader.document_index),
                "artifact_root": str(self.config.artifact_root),
                "metrics": rt.metrics.snapshot(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"enabled": True, "error": str(exc)}
