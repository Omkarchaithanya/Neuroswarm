"""Streaming speculative accept — TTFT before full target block."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from neuroswarm_arm.runtime.armcascade.config.loader import load_ascr_config, parse_escalation_graphs
from neuroswarm_arm.runtime.armcascade.engine import ASCREngine
from neuroswarm_arm.runtime.armcascade.interfaces.types import Proposal, ProposalToken
from neuroswarm_arm.runtime.armcascade.proposal import draft_model as _draft  # noqa: F401
from neuroswarm_arm.runtime.armcascade.verification import logits_verifier as _logits  # noqa: F401
from neuroswarm_arm.runtime.armcascade.verification import strategies as _verify  # noqa: F401
from neuroswarm_arm.runtime.dipa.cascade.cascade_policy import TierPolicy
from neuroswarm_arm.runtime.dipa.cascade.cascade_executor import CascadeExecutor
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    ExecutionPlan,
    GenerateRequest,
    GenerateResult,
    InferenceRequest,
    TokenChunk,
)


STEP_DELAY_S = 0.05  # synthetic per-token target delay


class _StreamingLogitsBackend:
    """Yields fixed logprob steps with delays — models streaming target."""

    def __init__(self, name: str, tier: int, steps: list[tuple[str, list[tuple[str, float, int]]]]) -> None:
        self.name = name
        self.tier = tier
        self._steps = steps
        self.draft_calls = 0
        self.stream_calls = 0

    async def generate(self, req: GenerateRequest, ctx: Any) -> GenerateResult:
        self.draft_calls += 1
        # Fast draft: return draft words immediately (no per-step delay).
        words = [s[0] for s in self._steps[:-1]]  # exclude bonus
        text = " ".join(words)
        return GenerateResult(
            text=text,
            backend=self.name,
            tier_used=self.tier,
            raw={"choices": [{"message": {"content": text}}]},
            metrics={},
            latency_ms=5.0,
        )

    async def generate_with_logits_stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.2,
        top_logprobs: int = 5,
        session_id: str = "",
        quant: str = "",
        kv_handle: str | None = None,
        id_slot: int | None = None,
        ctx: Any = None,
        draft: Any = None,
        tau_floor: float = 0.0,
    ):
        from neuroswarm_arm.runtime.armcascade.interfaces.types import LogitsBundle
        from neuroswarm_arm.runtime.armcascade.verification.logits_verifier import (
            accept_one_draft_position,
            _parse_step,
        )

        self.stream_calls += 1
        prop = draft
        words = [t.text for t in prop.tokens] if prop and prop.tokens else []
        bundle = LogitsBundle(
            draft_tokens=words,
            draft_token_ids=[t.token_id if t.token_id is not None else hash(t.text) for t in (prop.tokens or [])],
            draft_logprobs=[float(t.logprob or 0.0) for t in (prop.tokens or [])],
            draft_ranks=[int(t.rank) for t in (prop.tokens or [])],
            top_n=top_logprobs,
        )
        position = 0
        index = 0
        for step_i, (token, top) in enumerate(self._steps[: max(max_tokens, 1)]):
            await asyncio.sleep(STEP_DELAY_S)
            entry = {
                "token": token,
                "logprob": top[0][1],
                "top_logprobs": [
                    {"token": t, "logprob": lp, "token_id": tid} for t, lp, tid in top
                ],
            }
            step = _parse_step(entry)
            assert step is not None
            bundle.steps.append(step)
            while True:
                pos = accept_one_draft_position(
                    bundle, prop, position, greedy=True, tau_floor=tau_floor
                )
                if pos.waiting:
                    break
                if pos.accepted_token is not None:
                    yield TokenChunk(
                        text=pos.accepted_token,
                        index=index,
                        finished=False,
                        metrics={"accepted_prefix_len": float(position + 1)},
                    )
                    index += 1
                    position += 1
                    if pos.top_tau_used and pos.residual_or_bonus:
                        yield TokenChunk(
                            text=pos.residual_or_bonus,
                            index=index,
                            finished=False,
                            metrics={
                                "accepted_prefix_len": float(position),
                                "bonus": 1.0,
                            },
                        )
                        index += 1
                        yield TokenChunk(
                            text="",
                            index=index,
                            finished=True,
                            metrics={"accepted_prefix_len": float(position)},
                        )
                        return
                    if pos.is_final and position == len(bundle.draft_tokens):
                        # try bonus from current steps
                        bonus = accept_one_draft_position(
                            bundle, prop, position, greedy=True, tau_floor=tau_floor
                        )
                        if not bonus.waiting and bonus.residual_or_bonus:
                            yield TokenChunk(
                                text=bonus.residual_or_bonus,
                                index=index,
                                finished=False,
                                metrics={
                                    "accepted_prefix_len": float(position),
                                    "bonus": 1.0,
                                },
                            )
                            index += 1
                            yield TokenChunk(
                                text="",
                                index=index,
                                finished=True,
                                metrics={"accepted_prefix_len": float(position)},
                            )
                            return
                    break
                if pos.residual_or_bonus:
                    yield TokenChunk(
                        text=pos.residual_or_bonus,
                        index=index,
                        finished=False,
                        metrics={
                            "accepted_prefix_len": float(position),
                            "rejected": 1.0,
                        },
                    )
                    index += 1
                yield TokenChunk(
                    text="",
                    index=index,
                    finished=True,
                    metrics={"accepted_prefix_len": float(position)},
                )
                return
        yield TokenChunk(
            text="",
            index=index,
            finished=True,
            metrics={"accepted_prefix_len": float(position)},
        )


class _Registry:
    def __init__(self, backends: dict[str, Any]) -> None:
        self._backends = backends

    def require(self, name: str) -> Any:
        return self._backends[name]


def _paris_steps() -> list[tuple[str, list[tuple[str, float, int]]]]:
    return [
        ("Paris", [("Paris", -0.1, 1), ("London", -1.0, 2)]),
        ("is", [("is", -0.1, 10), ("was", -1.0, 11)]),
        ("the", [("the", -0.1, 20), ("a", -1.0, 21)]),
        ("capital", [("capital", -0.1, 30), ("city", -1.0, 31)]),
        ("bonus", [("bonus", -0.05, 40), ("x", -2.0, 41)]),
    ]


def test_streaming_first_chunk_before_full_target() -> None:
    steps = _paris_steps()
    n_target = len(steps)
    total_target_time = STEP_DELAY_S * n_target

    backend = _StreamingLogitsBackend("tier2", 2, steps)
    draft = Proposal(
        tokens=[
            ProposalToken(text="Paris", token_id=1, logprob=-0.1, rank=0),
            ProposalToken(text="is", token_id=10, logprob=-0.1, rank=0),
            ProposalToken(text="the", token_id=20, logprob=-0.1, rank=0),
            ProposalToken(text="capital", token_id=30, logprob=-0.1, rank=0),
        ],
        text="Paris is the capital",
        strategy="draft_model",
        draft_len=4,
        confidence=0.9,
        source_tier=1,
    )
    executor = CascadeExecutor(_Registry({"tier2": backend}))
    req = InferenceRequest(
        messages=[{"role": "user", "content": "capital?"}],
        max_tokens=16,
        temperature=0.0,
        session_id="stream-ttft",
    )
    ctx = ExecutionContext(request=req)
    tier = TierPolicy(id=2, backend="tier2", model="tier2")

    async def _run() -> tuple[float, list[str], int]:
        t0 = time.perf_counter()
        ttft = None
        texts: list[str] = []
        accepted = 0
        async for chunk in executor.generate_tier_stream(
            req, tier, ctx, draft, top_logprobs=2, max_tokens=5
        ):
            if chunk.text and ttft is None:
                ttft = time.perf_counter() - t0
            if chunk.text:
                texts.append(chunk.text)
            if chunk.metrics and "accepted_prefix_len" in chunk.metrics:
                accepted = int(chunk.metrics["accepted_prefix_len"])
            if chunk.finished:
                break
        return float(ttft or 0.0), texts, accepted

    ttft, texts, accepted = asyncio.run(_run())
    # First chunk after ~1 step delay, not after all steps.
    assert ttft < total_target_time * 0.6, f"ttft={ttft} total={total_target_time}"
    assert ttft < STEP_DELAY_S * 2.5
    # accepted_prefix + bonus
    assert len(texts) == accepted + 1, f"texts={texts} accepted={accepted}"
    assert texts == ["Paris", "is", "the", "capital", "bonus"]
    assert texts == sorted(texts, key=lambda t: texts.index(t))  # order preserved


def test_ascr_run_stream_order_and_count() -> None:
    steps = _paris_steps()
    backends = {
        "tier1": _StreamingLogitsBackend("tier1", 1, steps),
        "tier2": _StreamingLogitsBackend("tier2", 2, steps),
        "tier3": _StreamingLogitsBackend("tier3", 3, steps),
    }
    cfg = load_ascr_config()
    graphs = parse_escalation_graphs(cfg.get("escalation_graphs"))
    engine = ASCREngine(config=cfg, registry=_Registry(backends), graphs=graphs)
    plan = ExecutionPlan(
        model="tier1",
        backend="tier1",
        use_cascade=True,
        speculation=True,
        self_speculation=True,
        cascade_start_tier=1,
        stream=True,
        metadata={
            "speculation": {
                "strategy": "draft_model",
                "verify_strategy": "logits",
                "graph": "default_linear",
                "draft_len": 4,
            }
        },
    )
    req = InferenceRequest(
        messages=[{"role": "user", "content": "What is the capital?"}],
        max_tokens=32,
        temperature=0.0,
        session_id="ascr-stream",
        stream=True,
    )
    ctx = ExecutionContext(request=req)
    ctx.plan = plan

    async def _collect() -> tuple[list[str], float, int]:
        t0 = time.perf_counter()
        ttft = None
        texts: list[str] = []
        accepted = 0
        async for chunk in engine.run_stream(req, plan, ctx):
            if chunk.text and ttft is None:
                ttft = time.perf_counter() - t0
            if chunk.text:
                texts.append(chunk.text)
            if chunk.metrics and "accepted_prefix_len" in chunk.metrics:
                accepted = max(accepted, int(chunk.metrics["accepted_prefix_len"]))
            if chunk.finished:
                break
        return texts, float(ttft or 0.0), accepted

    texts, ttft, accepted = asyncio.run(_collect())
    total_target = STEP_DELAY_S * len(steps)
    assert ttft < total_target * 0.75, f"ttft={ttft} vs full={total_target}"
    assert len(texts) == accepted + 1
    assert texts[0] == "Paris"
    # No reordering
    assert texts == ["Paris", "is", "the", "capital", "bonus"]
