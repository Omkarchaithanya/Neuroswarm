"""ChunkPlanner — split long prompts for chunked prefill (delegates math to size budget)."""

from __future__ import annotations

from neuroswarm_arm.runtime.dipa.interfaces.pd import IChunkPlanner, PromptChunk
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest


class ChunkPlanner(IChunkPlanner):
    """Approximate token chunks by whitespace; SGLang owns real chunked-prefill scheduling."""

    def plan(self, req: InferenceRequest, *, chunk_size: int) -> list[PromptChunk]:
        size = max(64, int(chunk_size))
        messages = list(req.messages)
        if not messages:
            return [PromptChunk(index=0, total=1, messages=[], approx_tokens=0)]

        # Keep system / early messages intact; chunk only the trailing user content.
        prefix = messages[:-1]
        last = messages[-1]
        content = str(last.get("content", "") or "")
        words = content.split()
        if not words or len(words) <= size:
            approx = max(1, len(words)) if words else 0
            return [
                PromptChunk(
                    index=0,
                    total=1,
                    messages=messages,
                    approx_tokens=approx + _prefix_tokens(prefix),
                )
            ]

        chunks: list[PromptChunk] = []
        pieces = [words[i : i + size] for i in range(0, len(words), size)]
        total = len(pieces)
        for idx, piece in enumerate(pieces):
            text = " ".join(piece)
            # Cumulative prompt for recompute decode: full history up to this chunk.
            cumulative = " ".join(words[: (idx + 1) * size])
            chunk_messages = list(prefix) + [
                {**last, "content": cumulative if idx == total - 1 else text}
            ]
            if idx < total - 1:
                # Intermediate chunks send only the new segment + shared prefix roles.
                chunk_messages = list(prefix) + [{**last, "content": text}]
            chunks.append(
                PromptChunk(
                    index=idx,
                    total=total,
                    messages=chunk_messages,
                    approx_tokens=len(piece) + (_prefix_tokens(prefix) if idx == 0 else 0),
                )
            )
        # Final chunk must carry full cumulative user text for decode handoff.
        chunks[-1] = PromptChunk(
            index=total - 1,
            total=total,
            messages=list(prefix) + [{**last, "content": content}],
            approx_tokens=len(pieces[-1]),
        )
        return chunks


def _prefix_tokens(messages: list[dict[str, str]]) -> int:
    return sum(len(str(m.get("content", "")).split()) for m in messages)
