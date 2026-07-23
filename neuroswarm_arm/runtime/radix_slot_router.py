"""Radix trie slot router — prefix-aware llama-server id_slot reuse."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from neuroswarm_arm.runtime.slot_registry import SlotRegistry
from neuroswarm_arm.runtime.slot_router import SlotRouter

CHUNK_SIZE = 64


@dataclass(slots=True)
class _TrieNode:
    children: dict[tuple[int, ...], _TrieNode] = field(default_factory=dict)
    id_slot: int | None = None
    last_used: float = 0.0
    tail: tuple[int, ...] = ()


class RadixMetrics:
    """Lightweight in-process metrics for radix prefix routing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.prefix_hits = 0
        self.match_tokens: list[int] = []

    def record_hit(self, matched_len: int) -> None:
        with self._lock:
            self.prefix_hits += 1
            self.match_tokens.append(matched_len)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            tokens = list(self.match_tokens)
            hits = self.prefix_hits
        return {
            "radix_prefix_hit_total": hits,
            "radix_prefix_match_tokens": tokens,
        }


class RadixSlotRouter(SlotRouter):
    """Token-id radix trie wrapper over SlotRouter for cross-session prefix reuse.

    Trie nodes are keyed by 64-token chunks (batching heuristic for amortized lookup).
    """

    def __init__(
        self,
        registry: SlotRegistry | None = None,
        *,
        total_slots: int = 8,
        min_match: int | None = None,
        ttl_s: float | None = None,
        okf_affinity: Any | None = None,
    ) -> None:
        super().__init__(registry=registry, total_slots=total_slots)
        self._min_match = min_match if min_match is not None else int(
            os.getenv("NSA_RADIX_MIN_MATCH", "64")
        )
        self._ttl_s = ttl_s if ttl_s is not None else float(
            os.getenv("NSA_RADIX_TTL_S", "3600")
        )
        self._root = _TrieNode()
        self._lock = threading.RLock()
        self._metrics = RadixMetrics()
        self._okf_affinity = okf_affinity

    @property
    def metrics(self) -> RadixMetrics:
        return self._metrics

    def _split_tokens(self, token_ids: list[int]) -> tuple[list[tuple[int, ...]], tuple[int, ...]]:
        aligned = (len(token_ids) // CHUNK_SIZE) * CHUNK_SIZE
        full = [
            tuple(token_ids[i : i + CHUNK_SIZE])
            for i in range(0, aligned, CHUNK_SIZE)
        ]
        tail = tuple(token_ids[aligned:])
        return full, tail

    def _prune_expired(self, now: float) -> None:
        def _walk(node: _TrieNode) -> None:
            stale: list[tuple[int, ...]] = []
            for key, child in node.children.items():
                _walk(child)
                if child.id_slot is not None and (now - child.last_used) > self._ttl_s:
                    stale.append(key)
            for key in stale:
                del node.children[key]

        _walk(self._root)

    def prune_slot(self, id_slot: int) -> None:
        with self._lock:

            def _walk(node: _TrieNode) -> None:
                if node.id_slot == id_slot:
                    node.id_slot = None
                for child in node.children.values():
                    _walk(child)

            _walk(self._root)

    def insert(self, token_ids: list[int], id_slot: int) -> None:
        if not token_ids:
            return
        now = time.monotonic()
        full_chunks, tail = self._split_tokens(token_ids)
        with self._lock:
            node = self._root
            for chunk in full_chunks:
                if chunk not in node.children:
                    node.children[chunk] = _TrieNode()
                node = node.children[chunk]
                node.id_slot = id_slot
                node.last_used = now
            if tail:
                node.tail = tail
                node.id_slot = id_slot
                node.last_used = now
            self._prune_expired(now)

    def match_longest_prefix(self, token_ids: list[int]) -> tuple[int | None, int]:
        if not token_ids:
            return None, 0

        now = time.monotonic()
        best_slot: int | None = None
        best_len = 0
        node = self._root
        pos = 0
        full_chunks, tail = self._split_tokens(token_ids)

        with self._lock:
            for chunk in full_chunks:
                child = node.children.get(chunk)
                if child is None:
                    break
                pos += len(chunk)
                node = child
                if node.id_slot is not None and (now - node.last_used) <= self._ttl_s:
                    best_slot = node.id_slot
                    best_len = pos

            if node.tail and tail:
                common = 0
                for a, b in zip(node.tail, tail, strict=False):
                    if a != b:
                        break
                    common += 1
                if common and node.id_slot is not None and (now - node.last_used) <= self._ttl_s:
                    best_slot = node.id_slot
                    best_len = pos + common
            elif node.tail and not tail and node.id_slot is not None:
                best_slot = node.id_slot
                best_len = pos + len(node.tail)

        if best_slot is not None and best_len >= self._min_match:
            self._metrics.record_hit(best_len)
        return best_slot, best_len

    def prepare_payload(
        self,
        session_id: str,
        prompt: str,
        base_payload: dict[str, Any],
        *,
        token_ids: list[int] | None = None,
        okf_block_hashes: list[str] | None = None,
        affinity_hint: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ids = token_ids or []

        if okf_block_hashes and self._okf_affinity is not None:
            aff_slot = self._okf_affinity.lookup(okf_block_hashes)
            if aff_slot is not None:
                payload = dict(base_payload)
                payload["cache_prompt"] = True
                payload["id_slot"] = int(aff_slot)
                self._metrics.record_hit(len(ids) if ids else self._min_match)
                return payload, {
                    "slot_reused": True,
                    "slot_id": int(aff_slot),
                    "radix_match_len": len(ids),
                    "okf_affinity": True,
                }

        if ids:
            matched_slot, matched_len = self.match_longest_prefix(ids)
            if matched_slot is not None and matched_len >= self._min_match:
                payload = dict(base_payload)
                payload["cache_prompt"] = True
                payload["id_slot"] = int(matched_slot)
                return payload, {
                    "slot_reused": True,
                    "slot_id": int(matched_slot),
                    "radix_match_len": matched_len,
                }

        payload, telemetry = super().prepare_payload(
            session_id, prompt, base_payload, affinity_hint=affinity_hint
        )
        slot_id = telemetry.get("slot_id")
        if isinstance(slot_id, int) and ids:
            self.insert(ids, slot_id)
        return payload, telemetry

    def record_after_inference(
        self,
        token_ids: list[int],
        id_slot: int | None,
        *,
        okf_block_hashes: list[str] | None = None,
    ) -> None:
        if id_slot is None:
            return
        if token_ids:
            self.insert(token_ids, id_slot)
        if okf_block_hashes and self._okf_affinity is not None:
            self._okf_affinity.record(okf_block_hashes, id_slot)
