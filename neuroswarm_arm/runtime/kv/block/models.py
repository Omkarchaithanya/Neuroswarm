"""Logical KV block and per-session table."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..interfaces.types import BlockStatus, BlockTemperature, StorageTier, TensorMeta


@dataclass(slots=True)
class Block:
    """Fixed-size logical KV block (default 256 tokens)."""

    id: str
    layer: int
    head: int
    token_start: int
    token_end: int
    reference_count: int = 1
    content_hash: str = ""
    prefix_hash: str = ""
    storage_tier: StorageTier = StorageTier.L1_RAM
    status: BlockStatus = BlockStatus.ALLOCATED
    temperature: BlockTemperature = BlockTemperature.HOT
    physical_id: str | None = None
    numa_node: int = 0
    last_access: float = 0.0
    access_count: int = 0
    priority: int = 0
    meta: TensorMeta = field(default_factory=TensorMeta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "layer": self.layer,
            "head": self.head,
            "token_start": self.token_start,
            "token_end": self.token_end,
            "reference_count": self.reference_count,
            "content_hash": self.content_hash,
            "prefix_hash": self.prefix_hash,
            "storage_tier": int(self.storage_tier),
            "status": self.status.value,
            "temperature": self.temperature.value,
            "physical_id": self.physical_id,
            "numa_node": self.numa_node,
            "last_access": self.last_access,
            "access_count": self.access_count,
            "priority": self.priority,
            "meta": self.meta.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Block:
        return cls(
            id=str(data["id"]),
            layer=int(data.get("layer", 0)),
            head=int(data.get("head", 0)),
            token_start=int(data.get("token_start", 0)),
            token_end=int(data.get("token_end", 0)),
            reference_count=int(data.get("reference_count", 1)),
            content_hash=str(data.get("content_hash", "")),
            prefix_hash=str(data.get("prefix_hash", "")),
            storage_tier=StorageTier(int(data.get("storage_tier", StorageTier.L1_RAM))),
            status=BlockStatus(str(data.get("status", BlockStatus.ALLOCATED.value))),
            temperature=BlockTemperature(
                str(data.get("temperature", BlockTemperature.HOT.value))
            ),
            physical_id=data.get("physical_id"),
            numa_node=int(data.get("numa_node", 0)),
            last_access=float(data.get("last_access", 0.0)),
            access_count=int(data.get("access_count", 0)),
            priority=int(data.get("priority", 0)),
            meta=TensorMeta.from_dict(data.get("meta", {})),
        )


@dataclass
class SessionBlockTable:
    """Owns the logical block table for one session."""

    session_id: str
    agent_id: str = ""
    logical: list[str] = field(default_factory=list)  # logical block ids in order
    blocks: dict[str, Block] = field(default_factory=dict)
    block_size_tokens: int = 256
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "logical": list(self.logical),
            "blocks": {k: v.to_dict() for k, v in self.blocks.items()},
            "block_size_tokens": self.block_size_tokens,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionBlockTable:
        blocks = {
            k: Block.from_dict(v) for k, v in dict(data.get("blocks", {})).items()
        }
        return cls(
            session_id=str(data["session_id"]),
            agent_id=str(data.get("agent_id", "")),
            logical=list(data.get("logical", [])),
            blocks=blocks,
            block_size_tokens=int(data.get("block_size_tokens", 256)),
            created_at=float(data.get("created_at", 0.0)),
            updated_at=float(data.get("updated_at", 0.0)),
        )
