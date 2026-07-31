"""AWPP ToolWarmer records routed tool ids on Markov policy."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from neuroswarm_arm.runtime.awpp.policy.markov import MarkovPolicy
from neuroswarm_arm.runtime.awpp.warmers.tool import ToolWarmer
from neuroswarm_arm.runtime.router.models import RoutingResult, ScoredTool, ToolRecord


def test_router_warmer_records_tool_ids() -> None:
    markov = MarkovPolicy(min_observations=1)
    warmer = ToolWarmer(router=None, markov=markov)
    tool = ToolRecord(id="aws.s3.presign", name="s3_presign_url")
    rr = RoutingResult(
        tools=[ScoredTool(tool=tool, score=0.8, confidence=0.8)],
        confidence_top1=0.8,
    )
    warmer.record_router_result(rr)
    assert markov._last_tool.get("default") == "aws.s3.presign"


def test_warm_accepts_router_result_kwarg() -> None:
    markov = MarkovPolicy(min_observations=1)
    warmer = ToolWarmer(router=None, markov=markov)
    tool = ToolRecord(id="gh.create_issue", name="gh_create_issue")
    rr = RoutingResult(tools=[ScoredTool(tool=tool, score=0.7, confidence=0.7)])

    async def _run():
        return await warmer.warm("k", router_result=rr)

    result = asyncio.run(_run())
    assert result.success is True
    assert markov._last_tool.get("default") == "gh.create_issue"
