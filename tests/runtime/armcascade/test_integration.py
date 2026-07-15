"""Integration + stress tests for ASCR via DIPA mock backends."""

from __future__ import annotations

import asyncio

import pytest

from neuroswarm_arm.runtime.armcascade.engine import ASCREngine
from neuroswarm_arm.runtime.armcascade.factory import build_ascr
from neuroswarm_arm.runtime.armcascade.plugins import load_plugins
from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    ExecutionPlan,
    InferenceRequest,
    WorkloadClass,
)


def test_build_dipa_uses_ascr() -> None:
    rt = build_dipa(use_mock=True, start=True)
    try:
        assert isinstance(rt.cascade_engine, ASCREngine)
    finally:
        rt.shutdown()


def test_ascr_end_to_end_mock() -> None:
    rt = build_dipa(use_mock=True, start=True)
    try:
        req = InferenceRequest(
            messages=[{"role": "user", "content": "hello world what is 2+2"}],
            max_tokens=32,
            latency_sla_ms=5000,
            agent_role="tool_call",
        )
        resp = rt.infer(req)
        assert resp.text
        assert resp.tier_used >= 1
    finally:
        rt.shutdown()


def test_ascr_engine_direct_with_mocks() -> None:
    load_plugins()
    rt = build_dipa(use_mock=True, start=True)
    try:
        engine = build_ascr(rt.backends, dipa_cascade_cfg=rt.config.cascade)

        async def _run() -> None:
            req = InferenceRequest(
                messages=[
                    {
                        "role": "user",
                        "content": " ".join(f"token{i}" for i in range(40)),
                    }
                ],
                max_tokens=16,
            )
            plan = ExecutionPlan(
                workload=WorkloadClass.TOOL_CALLING,
                use_cascade=True,
                speculation=True,
                self_speculation=True,
                quant="Q4_K_M",
                metadata={
                    "speculation": {
                        "strategy": "self_speculation",
                        "verify_strategy": "quality",
                        "graph": "default_linear",
                        "draft_len": 8,
                    }
                },
            )
            ctx = ExecutionContext(request=req, plan=plan)
            result = await engine.run(req, plan, ctx)
            assert result.text
            assert (
                result.raw.get("ascr_mode")
                or result.metrics.get("confidence") is not None
            )

        asyncio.run(_run())
    finally:
        rt.shutdown()


def test_ascr_stress_concurrent() -> None:
    rt = build_dipa(use_mock=True, start=True)
    try:

        async def _run() -> list[str]:
            async def one(i: int) -> str:
                req = InferenceRequest(
                    messages=[
                        {"role": "user", "content": f"query number {i} please answer"}
                    ],
                    max_tokens=16,
                    session_id=f"s{i}",
                    agent_role="tool_call",
                )
                return await asyncio.to_thread(rt.infer, req)

            results = await asyncio.gather(*[one(i) for i in range(8)])
            return [r.text for r in results]

        texts = asyncio.run(_run())
        assert len(texts) == 8
        assert all(isinstance(t, str) and t for t in texts)
    finally:
        rt.shutdown()


def test_eagle_stub_raises() -> None:
    load_plugins()
    from neuroswarm_arm.runtime.armcascade.interfaces.types import (
        ASCRInitContext,
        ProposalRequest,
    )
    from neuroswarm_arm.runtime.armcascade.proposal.stubs import EagleProposer

    async def _run() -> None:
        p = EagleProposer()
        await p.initialize(ASCRInitContext())
        with pytest.raises(NotImplementedError):
            await p.propose(
                ProposalRequest(
                    prompt_text="x",
                    messages=[{"role": "user", "content": "x"}],
                    draft_len=4,
                    max_tokens=4,
                )
            )

    asyncio.run(_run())
