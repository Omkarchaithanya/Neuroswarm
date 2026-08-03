"""SpecInfer-style token tree + TreeAcceptor (Miao et al., ASPLOS 2024)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(slots=True)
class TokenTree:
    """Draft token tree: nodes=(token_id, parent_idx, draft_logprob)."""

    nodes: list[tuple[int, int, float]] = field(default_factory=list)
    children: list[list[int]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.nodes)

    @property
    def depth(self) -> int:
        if not self.nodes:
            return 0
        depths = [0] * len(self.nodes)
        for i, (_tid, parent, _lp) in enumerate(self.nodes):
            if parent < 0:
                depths[i] = 1
            else:
                depths[i] = depths[parent] + 1
        return max(depths) if depths else 0

    @property
    def width_avg(self) -> float:
        if not self.children:
            return 0.0
        widths = [len(c) for c in self.children if c]
        if not widths:
            return 0.0
        return sum(widths) / len(widths)

    @property
    def branches_total(self) -> int:
        """Leaf count (paths from root)."""
        if not self.nodes:
            return 0
        leaves = 0
        for i, kids in enumerate(self.children):
            if not kids:
                leaves += 1
        return leaves

    def node_depth(self, idx: int) -> int:
        d = 0
        cur = idx
        seen = 0
        while cur >= 0 and seen <= len(self.nodes):
            d += 1
            cur = self.nodes[cur][1]
            seen += 1
        return d

    def dfs_order(self) -> list[int]:
        if not self.nodes:
            return []
        roots = [i for i, (_t, p, _lp) in enumerate(self.nodes) if p < 0]
        order: list[int] = []

        def _dfs(i: int) -> None:
            order.append(i)
            for c in self.children[i]:
                _dfs(c)

        for r in roots:
            _dfs(r)
        return order


class TreeBuilder:
    """Incremental construction of a TokenTree."""

    def __init__(self) -> None:
        self.tree = TokenTree()

    def add_root(
        self,
        token_id: int,
        logprob: float = 0.0,
        text: str = "",
    ) -> int:
        idx = len(self.tree.nodes)
        self.tree.nodes.append((int(token_id), -1, float(logprob)))
        self.tree.children.append([])
        self.tree.texts.append(text or str(token_id))
        return idx

    def extend(
        self,
        parent_idx: int,
        token_ids: Sequence[int],
        logprobs: Sequence[float],
        texts: Sequence[str] | None = None,
    ) -> list[int]:
        if parent_idx < 0 or parent_idx >= len(self.tree.nodes):
            raise IndexError(f"parent_idx out of range: {parent_idx}")
        created: list[int] = []
        for i, tid in enumerate(token_ids):
            lp = float(logprobs[i]) if i < len(logprobs) else 0.0
            txt = ""
            if texts is not None and i < len(texts):
                txt = str(texts[i])
            idx = len(self.tree.nodes)
            self.tree.nodes.append((int(tid), int(parent_idx), lp))
            self.tree.children.append([])
            self.tree.texts.append(txt or str(tid))
            self.tree.children[parent_idx].append(idx)
            created.append(idx)
        return created

    def build(self) -> TokenTree:
        return self.tree


@dataclass(slots=True)
class AcceptedPath:
    node_indices: list[int] = field(default_factory=list)
    token_ids: list[int] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    depth: int = 0


@dataclass(slots=True)
class TreeAcceptResult:
    path: AcceptedPath
    bonus: str = ""
    bonus_token_id: int | None = None


def _normalized_mass(logprobs: Sequence[float]) -> list[float]:
    if not logprobs:
        return []
    m = max(logprobs)
    exps = [math.exp(lp - m) for lp in logprobs]
    total = sum(exps)
    if total <= 0:
        n = len(exps)
        return [1.0 / n for _ in exps]
    return [e / total for e in exps]


def _find_top_entry(
    topn: Sequence[tuple[int, float, str]],
    token_id: int,
) -> tuple[int, float, str] | None:
    for tid, lp, text in topn:
        if int(tid) == int(token_id):
            return (tid, lp, text)
    return None


def _argmax_topn(
    topn: Sequence[tuple[int, float, str]],
) -> tuple[int, float, str] | None:
    if not topn:
        return None
    return max(topn, key=lambda t: t[1])


class TreeAcceptor:
    """SpecInfer accept: DFS, longest consistent path + bonus token."""

    def accept(
        self,
        tree: TokenTree,
        target_topn_per_position: Sequence[Sequence[tuple[int, float, str]]],
        *,
        greedy: bool = False,
        rng: random.Random | None = None,
    ) -> TreeAcceptResult:
        rng = rng or random.Random()
        if not tree.nodes or not target_topn_per_position:
            return TreeAcceptResult(path=AcceptedPath())

        roots = [i for i, (_t, p, _lp) in enumerate(tree.nodes) if p < 0]
        best = AcceptedPath()

        for root in roots:
            path = self._try_from(
                tree,
                root,
                depth=0,
                target_topn_per_position=target_topn_per_position,
                greedy=greedy,
                rng=rng,
                prefix_nodes=[],
                prefix_ids=[],
                prefix_texts=[],
            )
            if path.depth > best.depth:
                best = path

        bonus = ""
        bonus_id: int | None = None
        # Bonus when we have target mass one step past accepted path.
        next_pos = best.depth
        if next_pos < len(target_topn_per_position):
            # Prefer bonus when path ends (leaf) or full greedy match exhausted children.
            at_leaf = True
            if best.node_indices:
                last = best.node_indices[-1]
                at_leaf = not tree.children[last]
            # SpecInfer / Leviathan: always offer bonus from next target top-1
            # when at least one token accepted OR empty path with target mass.
            if best.depth > 0 or at_leaf:
                top1 = _argmax_topn(target_topn_per_position[next_pos])
                if top1 is not None:
                    bonus_id = int(top1[0])
                    bonus = top1[2] or str(bonus_id)

        # When all branches match to a leaf, bonus is from position == path.depth
        # (already handled). For "all matching ΓåÆ bonus top-1" tests, ensure
        # we sample from the position after the path.
        if best.depth > 0 and best.depth <= len(target_topn_per_position):
            idx = best.depth  # next after last accepted (0-indexed depth count)
            if idx < len(target_topn_per_position):
                top1 = _argmax_topn(target_topn_per_position[idx])
                if top1 is not None:
                    bonus_id = int(top1[0])
                    bonus = top1[2] or str(bonus_id)

        return TreeAcceptResult(path=best, bonus=bonus, bonus_token_id=bonus_id)

    def _try_from(
        self,
        tree: TokenTree,
        node_idx: int,
        *,
        depth: int,
        target_topn_per_position: Sequence[Sequence[tuple[int, float, str]]],
        greedy: bool,
        rng: random.Random,
        prefix_nodes: list[int],
        prefix_ids: list[int],
        prefix_texts: list[str],
    ) -> AcceptedPath:
        """Accept ``node_idx`` against target at ``depth``, then DFS children."""
        if depth >= len(target_topn_per_position):
            return AcceptedPath(
                node_indices=list(prefix_nodes),
                token_ids=list(prefix_ids),
                texts=list(prefix_texts),
                depth=len(prefix_nodes),
            )

        tid, _parent, draft_lp = tree.nodes[node_idx]
        topn = target_topn_per_position[depth]
        if not self._accept_token(
            token_id=tid,
            draft_logprob=draft_lp,
            topn=topn,
            greedy=greedy,
            rng=rng,
        ):
            return AcceptedPath(
                node_indices=list(prefix_nodes),
                token_ids=list(prefix_ids),
                texts=list(prefix_texts),
                depth=len(prefix_nodes),
            )

        new_nodes = prefix_nodes + [node_idx]
        new_ids = prefix_ids + [tid]
        txt = tree.texts[node_idx] if node_idx < len(tree.texts) else str(tid)
        new_texts = prefix_texts + [txt]
        current = AcceptedPath(
            node_indices=new_nodes,
            token_ids=new_ids,
            texts=new_texts,
            depth=len(new_nodes),
        )

        kids = tree.children[node_idx] if node_idx < len(tree.children) else []
        if not kids:
            return current

        best = current
        for child in kids:
            cand = self._try_from(
                tree,
                child,
                depth=depth + 1,
                target_topn_per_position=target_topn_per_position,
                greedy=greedy,
                rng=rng,
                prefix_nodes=new_nodes,
                prefix_ids=new_ids,
                prefix_texts=new_texts,
            )
            if cand.depth > best.depth:
                best = cand
        return best

    @staticmethod
    def _accept_token(
        *,
        token_id: int,
        draft_logprob: float,
        topn: Sequence[tuple[int, float, str]],
        greedy: bool,
        rng: random.Random,
    ) -> bool:
        if greedy:
            argmax = _argmax_topn(topn)
            if argmax is None:
                return False
            return int(argmax[0]) == int(token_id)

        entry = _find_top_entry(topn, token_id)
        if entry is None:
            return False
        q = float(entry[1])
        p = float(draft_logprob)
        ratio = min(1.0, math.exp(q - p))
        return rng.random() < ratio


def linear_tree_from_tokens(
    token_ids: Sequence[int],
    logprobs: Sequence[float] | None = None,
    texts: Sequence[str] | None = None,
) -> TokenTree:
    """Build a depth-N chain (branching=1) from a flat draft."""
    b = TreeBuilder()
    if not token_ids:
        return b.build()
    lp0 = float(logprobs[0]) if logprobs else 0.0
    t0 = texts[0] if texts else str(token_ids[0])
    parent = b.add_root(int(token_ids[0]), lp0, t0)
    for i in range(1, len(token_ids)):
        lp = float(logprobs[i]) if logprobs and i < len(logprobs) else 0.0
        txt = texts[i] if texts and i < len(texts) else str(token_ids[i])
        created = b.extend(parent, [int(token_ids[i])], [lp], [txt])
        parent = created[0]
    return b.build()
