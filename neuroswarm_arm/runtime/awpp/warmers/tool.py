"""Tool warmer — prefetch semantic MCP Top-K schemas into a request-local cache."""

from __future__ import annotations

import time
from typing import Any, Mapping

from neuroswarm_arm.runtime.awpp.interfaces import IWarmer, WarmResult


class ToolWarmer(IWarmer):
    """Warm tool schemas via SemanticToolRouter / SemanticMCPRouter — no MCP execute."""

    kind = "tool"

    def __init__(
        self,
        router: Any | None = None,
        *,
        top_k: int = 3,
        ttl_s: float = 60.0,
    ) -> None:
        self.router = router
        self.top_k = top_k
        self.ttl_s = ttl_s
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def bind(self, router: Any) -> None:
        self.router = router

    async def warm(self, key: str, *, metadata: Mapping[str, Any] | None = None) -> WarmResult:
        t0 = time.perf_counter()
        meta = dict(metadata or {})
        query = str(meta.get("query") or key)
        if self.router is None:
            self._cache[key] = (time.time() + self.ttl_s, [])
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=True,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                metadata={"schemas": 0, "mode": "noop"},
            )
        try:
            schemas: list[dict[str, Any]] = []
            if hasattr(self.router, "route_result"):
                result = self.router.route_result(query)
                tools = getattr(result, "tools", None) or []
                for scored in tools[: self.top_k]:
                    tool = getattr(scored, "tool", scored)
                    if hasattr(tool, "model_dump"):
                        schemas.append(tool.model_dump())
                    elif hasattr(tool, "to_dict"):
                        schemas.append(tool.to_dict())
                    elif isinstance(tool, dict):
                        schemas.append(dict(tool))
                    else:
                        schemas.append(
                            {
                                "id": getattr(tool, "id", ""),
                                "name": getattr(tool, "name", str(tool)),
                                "description": getattr(tool, "description", ""),
                            }
                        )
            elif hasattr(self.router, "route"):
                tools = self.router.route(query) or []
                for tool in list(tools)[: self.top_k]:
                    if hasattr(tool, "model_dump"):
                        schemas.append(tool.model_dump())
                    elif isinstance(tool, dict):
                        schemas.append(dict(tool))
                    else:
                        schemas.append({"name": str(tool)})
            self._cache[key] = (time.time() + self.ttl_s, schemas)
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=True,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                bytes_touched=sum(len(str(s)) for s in schemas),
                metadata={"schemas": len(schemas), "mode": "route"},
            )
        except Exception as exc:  # noqa: BLE001
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=False,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )

    def is_warm(self, key: str) -> bool:
        entry = self._cache.get(key)
        if entry is None:
            return False
        expires, _ = entry
        if time.time() > expires:
            self._cache.pop(key, None)
            return False
        return True

    def get_schemas(self, key: str) -> list[dict[str, Any]]:
        if not self.is_warm(key):
            return []
        return list(self._cache[key][1])
