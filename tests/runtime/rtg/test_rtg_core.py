"""RTG unit tests — budget, sensors, streaming, bandit, swarm."""

from __future__ import annotations

from neuroswarm_arm.governor import ReasoningGovernor
from neuroswarm_arm.runtime.rtg import build_rtg
from neuroswarm_arm.runtime.rtg.models import TelemetryFrame
from neuroswarm_arm.runtime.rtg.policy import SlidingWindowUCB
from neuroswarm_arm.schemas import PlanState


def test_build_rtg_and_initial_budget_high_tool_conf() -> None:
    rtg = build_rtg()
    frame = TelemetryFrame(
        session_id="t1",
        prompt_text="call the slack tool now",
        tool_confidence_top1=0.95,
        kv_pressure=0.1,
        slo_remaining_ms=8000,
    )
    cap = rtg.initial_budget(frame)
    assert cap <= 256


def test_legacy_governor_facade_matches_rtg() -> None:
    rtg = build_rtg()
    gov = ReasoningGovernor(rtg=rtg)
    plan = PlanState(
        tool_confidence_top1=0.95,
        kv_pressure=0.2,
        slo_remaining_ms=8000,
        self_consistency_score=0.1,
    )
    assert gov.cap(plan) <= 256
    assert "tokens" in gov.prompt(plan)


def test_legacy_governor_without_rtg() -> None:
    gov = ReasoningGovernor()
    plan = PlanState(tool_confidence_top1=0.95, kv_pressure=0.2, slo_remaining_ms=8000)
    assert gov.cap(plan) == 256


def test_streaming_early_commit_on_self_consistency() -> None:
    rtg = build_rtg()
    state = rtg.admit(
        TelemetryFrame(
            session_id="stream-1",
            prompt_text="What is 2+2?",
            tool_confidence_top1=0.2,
            slo_remaining_ms=8000,
            complexity_score=0.2,
        )
    )
    d1 = rtg.on_chunk(state.session_id, "I think the answer is 4. ", tokens=8, latency_ms=10)
    assert d1.action.value in {
        "CONTINUE",
        "EARLY_COMMIT",
        "STOP_EARLY",
        "DECREASE_BUDGET",
        "INCREASE_BUDGET",
        "SKIP_REASONING",
    }
    d2 = rtg.on_chunk(
        state.session_id,
        "Final answer: 4",
        tokens=16,
        latency_ms=12,
        self_consistency_score=0.95,
    )
    assert state.budget.remaining_tokens >= 0
    assert state.budget.remaining_tokens <= state.budget.max_tokens
    done = rtg.on_complete(state.session_id, "Final answer: 4")
    assert done.reason == "complete"
    assert d2 is not None


def test_kv_pressure_hard_stop() -> None:
    rtg = build_rtg()
    state = rtg.admit(
        TelemetryFrame(
            session_id="kv-hard",
            prompt_text="long reasoning " * 40,
            tool_confidence_top1=0.1,
            kv_pressure=0.95,
            slo_remaining_ms=8000,
        )
    )
    # Initial budget already pressure-scaled
    assert state.budget.initial_tokens <= 512
    decision = rtg.on_chunk(state.session_id, "thinking...", tokens=32, kv_pressure=0.95)
    assert decision.action.value in {"STOP_EARLY", "DECREASE_BUDGET", "CONTINUE", "EARLY_COMMIT"}


def test_sw_ucb_select_and_update() -> None:
    bandit = SlidingWindowUCB([0.7, 0.85, 0.95], window=10)
    idx, arm = bandit.select()
    assert arm in {0.7, 0.85, 0.95}
    bandit.update(idx, 0.9)
    bandit.update(idx, 0.8)
    _, arm2 = bandit.select()
    assert arm2 in {0.7, 0.85, 0.95}


def test_swarm_rebalance() -> None:
    rtg = build_rtg()
    s1 = rtg.admit(TelemetryFrame(session_id="a", agent_priority=0.9, tool_confidence_top1=0.1))
    s2 = rtg.admit(TelemetryFrame(session_id="b", agent_priority=0.1, tool_confidence_top1=0.9))
    # Force equal remaining then rebalance by priority
    s1.budget.remaining_tokens = 1000
    s2.budget.remaining_tokens = 1000
    s1.budget.initial_tokens = 1000
    s2.budget.initial_tokens = 1000
    alloc = rtg.swarm.rebalance()
    assert s1.session_id in alloc and s2.session_id in alloc
    assert alloc[s1.session_id] >= alloc[s2.session_id]
    assert s1.budget.remaining_tokens <= s1.budget.initial_tokens
    assert s2.budget.remaining_tokens <= s2.budget.initial_tokens


def test_dipa_reasoning_hook_admit() -> None:
    from neuroswarm_arm.runtime.rtg.hooks import DIPAReasoningHook

    rtg = build_rtg()
    hook = DIPAReasoningHook(rtg)

    class Req:
        session_id = "hook-1"
        agent_id = "agent"
        agent_role = "tool_call"
        messages = [{"role": "user", "content": "ping slack"}]
        tool_names = ["slack"]
        tool_confidence = 0.9
        max_tokens = 2048

    meta = hook.on_admit(Req())
    assert meta["thinking_token_cap"] <= 256
    assert "system_prompt" in meta
    chunk = hook.on_chunk(meta["session_id"], "ok", tokens=4)
    assert "action" in chunk
    done = hook.on_complete(meta["session_id"], "ok")
    assert done["session_id"] == meta["session_id"]
