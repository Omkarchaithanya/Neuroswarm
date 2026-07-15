"""KnowledgeContext — institutional knowledge references (no retrieval)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .models import ContextRefKind, ExternalRef, _Base


class KnowledgeDocumentRef(_Base):
    doc_id: str = ""
    path: str = ""
    namespace: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalMeta(_Base):
    """Retrieval metadata only — no query execution."""

    query: str = ""
    top_k: int = 0
    strategy: str = ""
    hit_count: int = 0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeContext(_Base):
    """Namespaces, docs, policies, prompts, workflows, embeddings refs."""

    namespaces: list[str] = Field(default_factory=list)
    documents: list[KnowledgeDocumentRef] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    embedding_model: str = ""
    embedding_refs: list[str] = Field(default_factory=list)
    retrieval: RetrievalMeta = Field(default_factory=RetrievalMeta)
    knowledge_reference: ExternalRef = Field(
        default_factory=lambda: ExternalRef(kind=ContextRefKind.KNOWLEDGE)
    )
    okf_reference: ExternalRef = Field(
        default_factory=lambda: ExternalRef(kind=ContextRefKind.OKF)
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
