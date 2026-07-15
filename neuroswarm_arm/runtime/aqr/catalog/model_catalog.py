"""ModelCatalog — discover GGUF models from filesystem + env tier paths."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

from ..models import ModelEntry

_SIZE_RE = re.compile(
    r"(?P<size>\d+(?:\.\d+)?)\s*[bB](?:illion)?|(?P<small>\d+(?:\.\d+)?)[bB](?![a-zA-Z])",
    re.IGNORECASE,
)
_QUANT_TOKEN_RE = re.compile(
    r"(q\d+_k(?:_[ms])?|q\d+_[01]|q\d+|f16|fp16|bf16|int8|int4)",
    re.IGNORECASE,
)


class ModelCatalog:
    def __init__(
        self,
        discovery_cfg: Mapping[str, Any] | None = None,
        *,
        routing_hints: Mapping[str, Any] | None = None,
        extra_paths: list[str] | None = None,
    ) -> None:
        self._discovery = dict(discovery_cfg or {})
        self._routing = dict(routing_hints or {})
        self._aliases = {
            str(k).lower(): str(v)
            for k, v in (self._discovery.get("quant_aliases") or {}).items()
        }
        self._entries: dict[str, ModelEntry] = {}
        self._extra_paths = list(extra_paths or [])
        self.refresh()

    def refresh(self) -> None:
        self._entries.clear()
        self._ingest_tier_env()
        self._scan_dirs()
        self._apply_routing_hints()

    def get(self, name: str) -> ModelEntry | None:
        return self._entries.get(name)

    def list(self) -> list[ModelEntry]:
        return sorted(self._entries.values(), key=lambda e: (e.tier or 99, e.name))

    def find_by_quant(self, model: str, quant: str) -> ModelEntry | None:
        entry = self.get(model)
        if entry and entry.quant.upper() == quant.upper():
            return entry
        for e in self._entries.values():
            if e.name == model and e.quant.upper() == quant.upper():
                return e
            base = e.metadata.get("base_name", "")
            if base == model and e.quant.upper() == quant.upper():
                return e
        return entry

    def resolve_path(self, model: str, quant: str) -> str:
        hit = self.find_by_quant(model, quant)
        if hit and hit.path:
            return hit.path
        entry = self.get(model)
        return entry.path if entry else ""

    def _ingest_tier_env(self) -> None:
        tier_env = dict(self._discovery.get("tier_env") or {})
        for tier_name, env_key in tier_env.items():
            path = os.getenv(str(env_key), "")
            if not path:
                # Also check AppConfig-style defaults via NSA_MODEL_TIER*
                continue
            self._register_path(Path(path), alias=str(tier_name))

        # Always try NSA_MODEL_TIER* even if discovery yaml empty
        for i, name in enumerate(("tier1", "tier2", "tier3"), start=1):
            path = os.getenv(f"NSA_MODEL_TIER{i}", "")
            if path:
                self._register_path(Path(path), alias=name, tier=i)

    def _scan_dirs(self) -> None:
        dirs: list[str] = []
        for d in self._discovery.get("model_dirs") or []:
            text = str(d).strip()
            if text:
                dirs.append(text)
        if self._discovery.get("model_dir"):
            dirs.insert(0, str(self._discovery["model_dir"]))
        dirs.extend(self._extra_paths)
        env_dir = os.getenv("NSA_MODEL_DIR", "")
        if env_dir:
            dirs.insert(0, env_dir)

        patterns = [str(p) for p in (self._discovery.get("gguf_patterns") or ["*.gguf"])]
        seen: set[str] = set()
        for d in dirs:
            root = Path(d)
            if not root.exists() or not root.is_dir():
                continue
            key = str(root.resolve())
            if key in seen:
                continue
            seen.add(key)
            for pattern in patterns:
                for path in root.glob(pattern):
                    if path.is_file():
                        self._register_path(path)

    def _register_path(self, path: Path, *, alias: str | None = None, tier: int = 0) -> None:
        if not path.exists():
            # Still register alias pointing at missing path for planning
            if alias:
                quant = self._parse_quant(path.name)
                self._entries[alias] = ModelEntry(
                    name=alias,
                    path=str(path),
                    quant=quant or "Q4_K_M",
                    size_b=self._hint_size(alias),
                    tier=tier or self._tier_from_name(alias),
                    metadata={"missing": True, "base_name": alias},
                )
            return

        size_bytes = path.stat().st_size
        quant = self._parse_quant(path.name) or "Q4_K_M"
        size_b = self._parse_size_b(path.name) or max(0.1, size_bytes / (2.0 * 1e9))
        name = alias or path.stem.lower()
        ram = int(size_bytes * 1.25)
        kv_est = int(4096 * 2 * size_b * 1e6 * 0.05)  # rough
        entry = ModelEntry(
            name=name,
            path=str(path.resolve()) if path.exists() else str(path),
            quant=quant,
            size_bytes=size_bytes,
            size_b=size_b,
            ram_requirement_bytes=ram,
            kv_size_estimate_bytes=kv_est,
            tier=tier or self._tier_from_name(name),
            reasoning_capability=0.8 if size_b >= 7 else (0.6 if size_b >= 2 else 0.3),
            metadata={"base_name": alias or self._base_name(path.stem), "filename": path.name},
        )
        self._entries[name] = entry
        # Also index by tier alias if path matches tier env
        if alias and alias != name:
            self._entries[alias] = entry.model_copy(update={"name": alias})

    def _apply_routing_hints(self) -> None:
        models = dict(self._routing.get("models") or {})
        for name, raw in models.items():
            if not isinstance(raw, Mapping):
                continue
            existing = self._entries.get(str(name))
            size_b = float(raw.get("size_b", existing.size_b if existing else 1.0))
            roles = [str(r) for r in (raw.get("roles") or [])]
            reasoning = bool(raw.get("reasoning", False))
            if existing:
                existing.size_b = size_b
                existing.reasoning_capability = 0.9 if reasoning else existing.reasoning_capability
                existing.tool_calling_support = "tool_calling" in roles or existing.tool_calling_support
                existing.embedding_support = "embedding" in roles
                existing.vision_support = "vision" in roles
                existing.metadata["latency_hint_ms"] = float(raw.get("latency_hint_ms", 100))
                existing.metadata["cost_per_1k"] = float(raw.get("cost_per_1k", 0.001))
                existing.metadata["roles"] = roles
            else:
                self._entries[str(name)] = ModelEntry(
                    name=str(name),
                    size_b=size_b,
                    quant="Q5_K_M",
                    tier=self._tier_from_name(str(name)),
                    reasoning_capability=0.9 if reasoning else 0.5,
                    tool_calling_support="tool_calling" in roles or True,
                    embedding_support="embedding" in roles,
                    vision_support="vision" in roles,
                    metadata={
                        "latency_hint_ms": float(raw.get("latency_hint_ms", 100)),
                        "cost_per_1k": float(raw.get("cost_per_1k", 0.001)),
                        "roles": roles,
                        "from_routing_yaml": True,
                    },
                )

    def _parse_quant(self, filename: str) -> str:
        match = _QUANT_TOKEN_RE.search(filename.replace("-", "_"))
        if not match:
            return ""
        token = match.group(1).lower()
        return self._aliases.get(token, token.upper())

    def _parse_size_b(self, filename: str) -> float:
        match = _SIZE_RE.search(filename.replace("-", " "))
        if not match:
            return 0.0
        if match.group("size"):
            return float(match.group("size"))
        if match.group("small"):
            return float(match.group("small"))
        return 0.0

    @staticmethod
    def _tier_from_name(name: str) -> int:
        text = name.lower()
        for i in (1, 2, 3):
            if f"tier{i}" in text:
                return i
        return 0

    @staticmethod
    def _base_name(stem: str) -> str:
        return re.sub(r"[-_]q\d.*$", "", stem, flags=re.IGNORECASE)

    @staticmethod
    def _hint_size(alias: str) -> float:
        return {"tier1": 0.5, "tier2": 3.0, "tier3": 8.0}.get(alias, 1.0)
