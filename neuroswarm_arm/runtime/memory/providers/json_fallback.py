"""JSON emergency fallback — circuit-breaker ONLY when Mem0 unavailable.

Not a production peer to Mem0. Official path uses Mem0Adapter / Mem0Provider.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from neuroswarm_arm.runtime.memory.embeddings import cosine, hash_embed
from neuroswarm_arm.runtime.memory.namespace import normalize_namespace
from neuroswarm_arm.runtime.memory.schemas import MemoryRecord, SearchHit, SearchQuery


class JsonFallbackProvider:
    """Emergency ADD-only store under ``store_root/json/{owner}.json``."""

    name = "json_emergency"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._by_id: dict[str, MemoryRecord] = {}
        self._by_owner: dict[str, list[str]] = {}
        self._load_all()

    def _path(self, owner: str) -> Path:
        safe = owner.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.json"

    def _load_all(self) -> None:
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for item in payload:
                try:
                    rec = MemoryRecord.from_dict(item)
                except (TypeError, ValueError, KeyError):
                    continue
                self._index(rec)

    def _index(self, rec: MemoryRecord) -> None:
        self._by_id[rec.uuid] = rec
        self._by_owner.setdefault(rec.owner, [])
        if rec.uuid not in self._by_owner[rec.owner]:
            self._by_owner[rec.owner].append(rec.uuid)

    def _persist(self, owner: str) -> None:
        ids = self._by_owner.get(owner, [])
        payload = [self._by_id[i].to_dict() for i in ids if i in self._by_id]
        self._path(owner).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, record: MemoryRecord) -> MemoryRecord:
        with self._lock:
            if record.embedding is None:
                record.embedding = hash_embed(record.content)
            self._index(record)
            self._persist(record.owner)
            return record

    def add_messages(
        self,
        messages: str | list[dict[str, str]],
        *,
        owner: str,
        agent_id: str = "",
        run_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        if isinstance(messages, str):
            text = messages
        else:
            text = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
        rec = MemoryRecord(
            content=text.strip(),
            owner=owner,
            origin_agent=agent_id or owner,
            metadata={**(metadata or {}), "run_id": run_id, "source": "add_messages"},
            namespace="agents/",
        )
        return [self.add(rec)]

    def search(self, query: SearchQuery) -> list[SearchHit]:
        with self._lock:
            ids = list(self._by_owner.get(query.owner, []))
            q_emb = hash_embed(query.text)
            tokens = set(query.text.lower().split())
            hits: list[SearchHit] = []
            for mid in ids:
                rec = self._by_id.get(mid)
                if rec is None:
                    continue
                if rec.archived and not query.include_archived:
                    continue
                if query.namespace:
                    qns = normalize_namespace(query.namespace)
                    if rec.namespace != qns and not rec.namespace.startswith(qns.rstrip("/") + "/"):
                        # allow same root (e.g. tools/ vs tools/github/)
                        if not (rec.namespace.startswith(qns[: qns.find("/") + 1]) and qns.count("/") == 1):
                            if rec.namespace.split("/")[0] != qns.split("/")[0]:
                                continue
                if query.memory_types and rec.type not in query.memory_types:
                    continue
                if rec.importance < query.min_importance or rec.confidence < query.min_confidence:
                    continue
                if query.tags and not set(query.tags).intersection(rec.tags):
                    continue
                if query.workflow_id and rec.workflow_id != query.workflow_id:
                    continue
                emb = rec.embedding or hash_embed(rec.content)
                sem = cosine(q_emb, emb)
                kw = sum(1 for t in tokens if t in rec.content.lower()) / max(1, len(tokens))
                score = 0.6 * sem + 0.4 * kw
                if score <= 0 and tokens:
                    # still return weak keyword matches for history ranker
                    score = kw
                hits.append(SearchHit(record=rec, score=score, signals={"semantic": sem, "keyword": kw}))
            hits.sort(key=lambda h: h.score, reverse=True)
            return hits[: query.limit]

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            return self._by_id.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            rec = self._by_id.pop(memory_id, None)
            if rec is None:
                return False
            owner_ids = self._by_owner.get(rec.owner, [])
            if memory_id in owner_ids:
                owner_ids.remove(memory_id)
            self._persist(rec.owner)
            return True

    def list_ids(self, *, owner: str = "", namespace: str = "") -> list[str]:
        with self._lock:
            if owner:
                ids = list(self._by_owner.get(owner, []))
            else:
                ids = list(self._by_id.keys())
            if not namespace:
                return ids
            ns = normalize_namespace(namespace)
            return [i for i in ids if self._by_id[i].namespace == ns]

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": self.name,
                "records": len(self._by_id),
                "owners": len(self._by_owner),
                "root": str(self.root),
                "healthy": True,
            }
