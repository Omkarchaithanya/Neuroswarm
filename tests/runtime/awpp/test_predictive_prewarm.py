"""AWPP Phase-1 unit tests — connector, warmers, budget, observation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from neuroswarm_arm.runtime.awpp.actions import WarmTarget, WarmTargetKind
from neuroswarm_arm.runtime.awpp.config import AWPPRuntimeConfig
from neuroswarm_arm.runtime.awpp.interfaces import PrewarmBudget, WarmResult
from neuroswarm_arm.runtime.awpp.observation import Observation
from neuroswarm_arm.runtime.awpp.policy import FrequencyPolicy, MarkovPolicy
from neuroswarm_arm.runtime.awpp.state import AWPPState
from neuroswarm_arm.runtime.awpp.warmers import (
    MemoryWarmer,
    ModelWarmer,
    ToolWarmer,
    WarmerDispatcher,
)
from neuroswarm_arm.runtime.dipa.awpp.predictive_connector import PredictiveWarmConnector
from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan, InferenceRequest


def _req(**kwargs) -> InferenceRequest:
    base = dict(
        messages=[{"role": "user", "content": "list S3 buckets for the deploy"}],
        model="tier1",
        agent_id="agent-a",
        session_id="sess-1",
        agent_role="tool_call",
        tool_names=["s3.list"],
    )
    base.update(kwargs)
    return InferenceRequest(**base)


def _plan(**kwargs) -> ExecutionPlan:
    base = dict(model="tier1", backend="llama_cpp", quant="Q4_0")
    base.update(kwargs)
    return ExecutionPlan(**base)


@pytest.mark.asyncio
async def test_model_warmer_marks_warm_on_health() -> None:
    class _Resp:
        status_code = 200

    class _Http:
        async def get(self, url, timeout=None):
            assert "/health" in url
            return _Resp()

    warmer = ModelWarmer(urls={"tier1": "http://127.0.0.1:8081"}, http_client=_Http())
    result = await warmer.warm("tier1")
    assert result.success
    assert warmer.is_warm("tier1")


@pytest.mark.asyncio
async def test_memory_and_tool_warmers_noop_without_backends() -> None:
    mem = MemoryWarmer(memory=None)
    tool = ToolWarmer(router=None)
    mr = await mem.warm("deploy context", metadata={"agent_id": "a"})
    tr = await tool.warm("s3.list", metadata={"query": "list buckets"})
    assert mr.success and mem.is_warm("deploy context")
    assert tr.success and tool.is_warm("s3.list")


@pytest.mark.asyncio
async def test_dispatcher_budget_skip() -> None:
    class SlowWarmer:
        kind = "model"

        async def warm(self, key: str, *, metadata=None) -> WarmResult:
            await asyncio.sleep(0.05)
            return WarmResult(target_kind="model", target_key=key, success=True, latency_ms=50.0)

        def is_warm(self, key: str) -> bool:
            return False

    dispatcher = WarmerDispatcher(
        {"model": SlowWarmer()},
        budget=PrewarmBudget(max_cpu_fraction=0.01, rate_limit_per_s=100, timeout_s=2.0),
        window_s=1.0,
    )
    # First warm consumes ~50ms → 5% of 1s window → exceeds 1%
    first = await dispatcher.dispatch([WarmTarget(WarmTargetKind.MODEL, "tier1", 1.0)])
    assert first[0].success
    second = await dispatcher.dispatch([WarmTarget(WarmTargetKind.MODEL, "tier2", 1.0)])
    assert second[0].error == "budget_skip"
    assert dispatcher.skips_total >= 1


def test_frequency_and_markov_policy_learn() -> None:
    freq = FrequencyPolicy(min_observations=2)
    markov = MarkovPolicy(min_observations=2)
    for model, tool in [("tier1", "s3.list"), ("tier2", "github.pr"), ("tier1", "s3.list")]:
        obs = Observation(agent_id="a", model=model, tool=tool, event_type="inference_complete")
        freq.update(obs)
        markov.update(obs)
    state = AWPPState(agent_id="a", metadata={"last_model": "tier1", "last_tool": "s3.list"})
    fp = freq.act(state)
    mp = markov.act(state)
    assert not fp.action.skip
    assert fp.action.next_model == "tier1"
    assert not mp.action.skip
    assert mp.confidence > 0.0


@pytest.mark.asyncio
async def test_predictive_connector_warm_and_aqr_fields(tmp_path: Path) -> None:
    cfg = AWPPRuntimeConfig(root=tmp_path / "awpp")
    cfg.__post_init__()
    cfg.confidence_threshold = 0.0
    cfg.max_cpu_fraction = 0.5  # allow warmers in test
    cfg.warmup_urls = {"tier1": "http://127.0.0.1:9"}  # unused if noop model warmer

    class InstantModel:
        kind = "model"

        async def warm(self, key, *, metadata=None):
            return WarmResult(target_kind="model", target_key=key, success=True)

        def is_warm(self, key):
            return True

    conn = PredictiveWarmConnector(config=cfg)
    conn.dispatcher.register(InstantModel())
    # Seed policy so markov/freq does not skip
    for _ in range(4):
        conn.policy.update(
            Observation(agent_id="agent-a", model="tier1", tool="s3.list", event_type="x")
        )

    req = _req()
    plan = _plan()
    ok = await conn.ensure_warm(req, plan)
    assert ok
    assert conn.is_warm("tier1")
    assert req.baggage.get("awpp_prediction")
    assert req.baggage.get("model_warm_state", {}).get("tier1") is True
    assert plan.metadata.get("awpp_prediction")

    obs = conn.record_observation(req, plan, latency_ms=12.0, tools_used=["s3.list"], model="tier1")
    assert obs.model == "tier1"
    replay_files = list((tmp_path / "awpp" / "replay").glob("*.jsonl"))
    assert replay_files
    assert replay_files[0].read_text(encoding="utf-8").strip()

    status = conn.status()
    assert "policy" in status
    assert "warm_hits" in status or "dispatcher" in status


@pytest.mark.asyncio
async def test_connector_falls_back_on_predictor_failure(tmp_path: Path) -> None:
    cfg = AWPPRuntimeConfig(root=tmp_path / "awpp2")
    cfg.__post_init__()
    cfg.confidence_threshold = 0.99
    cfg.always_warm_tier1 = False

    class BoomPredictor:
        name = "boom"

        def predict(self, state):
            raise RuntimeError("boom")

        def update(self, observation):
            return None

    conn = PredictiveWarmConnector(config=cfg, predictor=BoomPredictor())
    # Empty policy history → predictor path → boom → heuristic fallback
    req = _req()
    plan = _plan(model="tier2")
    ok = await conn.ensure_warm(req, plan)
    assert ok
    assert conn.is_warm("tier2")
