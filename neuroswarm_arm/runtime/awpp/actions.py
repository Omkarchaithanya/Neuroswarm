"""AWPP multi-head prediction / prewarm actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class WarmTargetKind(str, Enum):
    MODEL = "model"
    QUANT = "quant"
    TOOL = "tool"
    KV = "kv"
    MEMORY = "memory"
    CONTEXT = "context"
    EMBEDDING = "embedding"
    BACKEND = "backend"
    CASCADE = "cascade"
    AGENT = "agent"
    PROMPT = "prompt"
    RESOURCE = "resource"


@dataclass(slots=True)
class WarmTarget:
    kind: WarmTargetKind
    key: str
    priority: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "key": self.key,
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WarmTarget:
        return cls(
            kind=WarmTargetKind(str(data.get("kind") or WarmTargetKind.MODEL.value)),
            key=str(data.get("key") or ""),
            priority=float(data.get("priority") or 0.0),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class AWPPAction:
    """Multi-head action: what to prewarm next."""

    targets: list[WarmTarget] = field(default_factory=list)
    next_model: str = ""
    next_quant: str = ""
    next_tool: str = ""
    next_backend: str = ""
    next_cascade_tier: int = 1
    next_agent: str = ""
    next_prompt_hint: str = ""
    kv_pages: list[str] = field(default_factory=list)
    memory_keys: list[str] = field(default_factory=list)
    okf_docs: list[str] = field(default_factory=list)
    resource_hint: dict[str, float] = field(default_factory=dict)
    skip: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "targets": [t.to_dict() for t in self.targets],
            "next_model": self.next_model,
            "next_quant": self.next_quant,
            "next_tool": self.next_tool,
            "next_backend": self.next_backend,
            "next_cascade_tier": self.next_cascade_tier,
            "next_agent": self.next_agent,
            "next_prompt_hint": self.next_prompt_hint,
            "kv_pages": list(self.kv_pages),
            "memory_keys": list(self.memory_keys),
            "okf_docs": list(self.okf_docs),
            "resource_hint": dict(self.resource_hint),
            "skip": self.skip,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AWPPAction:
        targets = [WarmTarget.from_dict(t) for t in (data.get("targets") or [])]
        return cls(
            targets=targets,
            next_model=str(data.get("next_model") or ""),
            next_quant=str(data.get("next_quant") or ""),
            next_tool=str(data.get("next_tool") or ""),
            next_backend=str(data.get("next_backend") or ""),
            next_cascade_tier=int(data.get("next_cascade_tier") or 1),
            next_agent=str(data.get("next_agent") or ""),
            next_prompt_hint=str(data.get("next_prompt_hint") or ""),
            kv_pages=[str(x) for x in (data.get("kv_pages") or [])],
            memory_keys=[str(x) for x in (data.get("memory_keys") or [])],
            okf_docs=[str(x) for x in (data.get("okf_docs") or [])],
            resource_hint={
                str(k): float(v) for k, v in dict(data.get("resource_hint") or {}).items()
            },
            skip=bool(data.get("skip") or False),
        )

    def all_targets(self) -> list[WarmTarget]:
        if self.targets:
            return list(self.targets)
        out: list[WarmTarget] = []
        if self.next_model:
            out.append(WarmTarget(WarmTargetKind.MODEL, self.next_model, 1.0))
        if self.next_quant:
            out.append(WarmTarget(WarmTargetKind.QUANT, self.next_quant, 0.9))
        if self.next_tool:
            out.append(WarmTarget(WarmTargetKind.TOOL, self.next_tool, 0.8))
        if self.next_backend:
            out.append(WarmTarget(WarmTargetKind.BACKEND, self.next_backend, 0.85))
        if self.next_cascade_tier:
            out.append(
                WarmTarget(
                    WarmTargetKind.CASCADE,
                    f"tier{self.next_cascade_tier}",
                    0.7,
                )
            )
        for page in self.kv_pages:
            out.append(WarmTarget(WarmTargetKind.KV, page, 0.75))
        for key in self.memory_keys:
            out.append(WarmTarget(WarmTargetKind.MEMORY, key, 0.7))
        for doc in self.okf_docs:
            out.append(WarmTarget(WarmTargetKind.CONTEXT, doc, 0.65))
        return out


def merge_actions(actions: Sequence[AWPPAction], *, weights: Sequence[float] | None = None) -> AWPPAction:
    """Merge multi-head predictions; higher weight wins per field."""
    if not actions:
        return AWPPAction(skip=True)
    w = list(weights) if weights is not None else [1.0] * len(actions)
    if len(w) != len(actions):
        w = [1.0] * len(actions)
    best = max(range(len(actions)), key=lambda i: w[i])
    primary = actions[best]
    seen: dict[tuple[str, str], WarmTarget] = {}
    for act, weight in zip(actions, w):
        if act.skip:
            continue
        for t in act.all_targets():
            key = (t.kind.value, t.key)
            scaled = WarmTarget(t.kind, t.key, t.priority * weight, dict(t.metadata))
            prev = seen.get(key)
            if prev is None or scaled.priority > prev.priority:
                seen[key] = scaled
    targets = sorted(seen.values(), key=lambda t: t.priority, reverse=True)
    if not targets and primary.skip:
        return AWPPAction(skip=True)
    return AWPPAction(
        targets=targets,
        next_model=primary.next_model or (targets[0].key if targets and targets[0].kind == WarmTargetKind.MODEL else ""),
        next_quant=primary.next_quant,
        next_tool=primary.next_tool,
        next_backend=primary.next_backend,
        next_cascade_tier=primary.next_cascade_tier,
        next_agent=primary.next_agent,
        next_prompt_hint=primary.next_prompt_hint,
        kv_pages=list(primary.kv_pages),
        memory_keys=list(primary.memory_keys),
        okf_docs=list(primary.okf_docs),
        resource_hint=dict(primary.resource_hint),
        skip=False,
    )
