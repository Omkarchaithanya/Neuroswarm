"""AROP unit tests — fail-loud parsers, tuner rules, dry-run cycles."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from neuroswarm_arm.arop.exceptions import AropMetricInvalid, AropMetricMissing
from neuroswarm_arm.arop.evolve_cycle import run_cycle
from neuroswarm_arm.arop.history import read_history
from neuroswarm_arm.arop.metrics_parser import (
    collect_bundle,
    load_json,
    parse_cascade_acceptance,
    parse_code_hotspots,
    parse_governor,
    parse_instruction_mix,
    read_tier_throughput,
    require,
)
from neuroswarm_arm.arop.policy_state import PolicyState, save_policy
from neuroswarm_arm.arop.tuner import apply_decision, decide

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_require_raises_on_missing():
    with pytest.raises(AropMetricMissing, match="missing required field"):
        require({"a": 1}, "b", "test")


def test_require_raises_on_null():
    with pytest.raises(AropMetricMissing, match="is null"):
        require({"a": None}, "a", "test")


def test_require_nested_ok():
    assert require({"summary": {"neon_pct": 3.41}}, "summary.neon_pct", "t") == 3.41


def test_parse_code_hotspots_real_apx_clean():
    data = load_json(FIXTURES / "code_hotspots_apx.json")
    # Real evidence has null IPC — parser must NOT read it / invent 0.
    assert data["summary"]["ipc"] is None
    m = parse_code_hotspots(data)
    assert m.source == "apx"
    assert "ggml" in m.top_function.lower()
    assert m.top_pct > 60
    assert m.unknown_symbol_pct < 20
    assert m.contaminated is False


def test_parse_code_hotspots_rejects_demo():
    with pytest.raises(AropMetricInvalid, match="source"):
        parse_code_hotspots(
            {
                "source": "demo",
                "hotspots": [{"function": "x", "pct": 50.0}],
            }
        )


def test_parse_code_hotspots_contaminated_posix():
    m = parse_code_hotspots(load_json(FIXTURES / "code_hotspots_contaminated.json"))
    assert m.contaminated is True
    assert m.contamination_reason is not None
    assert "posix_fallocate" in (m.contamination_reason or "")


def test_requesting_ipc_from_hotspots_raises():
    data = load_json(FIXTURES / "code_hotspots_apx.json")
    with pytest.raises(AropMetricMissing, match="null"):
        require(data, "summary.ipc", "code_hotspots")


def test_parse_instruction_mix():
    m = parse_instruction_mix(load_json(FIXTURES / "instruction_mix_apx.json"))
    assert m.neon_pct == 3.41
    assert m.sve_pct == 0.94
    assert abs(m.simd_instruction_pct - 4.35) < 1e-9
    assert not hasattr(m, "simd_util")


def test_parse_cascade_acceptance_derives_tier_rates():
    m = parse_cascade_acceptance(load_json(FIXTURES / "acceptance_high_t1.json"))
    assert m.sample_size == 10
    assert m.tier1_hit_rate == 0.7
    assert m.tier2_hit_rate == 0.2
    assert m.tier3_hit_rate == 0.1


def test_parse_cascade_missing_tier_used_raises():
    payload = load_json(FIXTURES / "acceptance_high_t1.json")
    payload["per_request"][0] = {"prompt_type": "x", "latency_ms": 1.0}
    with pytest.raises(AropMetricMissing, match="tier_used"):
        parse_cascade_acceptance(payload)


def test_parse_governor_maps_avg_tokens_run_b():
    m = parse_governor(load_json(FIXTURES / "governor_overrun.json"))
    assert m.thinking_tokens_avg == 5200.0
    assert m.cap_b_used == 4096


def test_read_tier_throughput_requires_metric():
    text = (FIXTURES / "llama_metrics.txt").read_text(encoding="utf-8")
    m = read_tier_throughput("http://127.0.0.1:8081", metrics_text=text)
    assert m.predicted_tokens_seconds == 42.5


def test_read_tier_throughput_missing_metric_raises():
    with pytest.raises(AropMetricMissing, match="predicted_tokens_seconds"):
        read_tier_throughput(
            "http://127.0.0.1:8081",
            metrics_text="# HELP foo\nllamacpp:prompt_tokens_total 1\n",
        )


@pytest.mark.parametrize(
    "path,field",
    [
        ("summary.ipc", "code_hotspots"),
        ("missing_key", "any"),
    ],
)
def test_never_returns_zero_for_absent(path, field):
    data = load_json(FIXTURES / "code_hotspots_apx.json")
    with pytest.raises(AropMetricMissing):
        require(data, path, field)


def test_tuner_r0_contaminated():
    bundle = collect_bundle(
        hotspots_path=FIXTURES / "code_hotspots_contaminated.json",
        acceptance_path=FIXTURES / "acceptance_low_t1.json",
    )
    d = decide(bundle, PolicyState(8, 0.7, 4096))
    assert d.action == "skip"
    assert d.rule_id == "R0"


def test_tuner_r1_shrink_draft_k():
    bundle = collect_bundle(
        hotspots_path=FIXTURES / "code_hotspots_apx.json",
        acceptance_path=FIXTURES / "acceptance_low_t1.json",
        instruction_mix_path=FIXTURES / "instruction_mix_apx.json",
    )
    assert bundle.cascade is not None
    assert bundle.cascade.tier1_hit_rate < 0.6
    d = decide(bundle, PolicyState(8, 0.7, 4096))
    assert d.action == "change"
    assert d.rule_id == "R1"
    assert d.param == "cascade_draft_k"
    assert d.before == 8
    assert d.after == 7


def test_tuner_r2_grow_draft_k():
    # High t1 + low latency; use hotspots that are clean but NOT ggml>60 to avoid R1.
    # Real apx has ggml>60 — so for R2 we need high t1; R1 also needs low t1.
    # With high t1, R1 won't fire even with ggml hot.
    bundle = collect_bundle(
        hotspots_path=FIXTURES / "code_hotspots_apx.json",
        acceptance_path=FIXTURES / "acceptance_high_t1.json",
    )
    # acceptance_high_t1 has tier1=0.7 — need >0.9 for R2. Build inline.
    payload = load_json(FIXTURES / "acceptance_high_t1.json")
    for row in payload["per_request"]:
        row["tier_used"] = 1
    payload["avg_latency_ms"] = 1000.0
    tmp = FIXTURES / "_tmp_acceptance_r2.json"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    try:
        bundle = collect_bundle(
            hotspots_path=FIXTURES / "code_hotspots_apx.json",
            acceptance_path=tmp,
        )
        d = decide(bundle, PolicyState(5, 0.7, 4096))
        assert d.action == "change"
        assert d.rule_id == "R2"
        assert d.param == "cascade_draft_k"
        assert d.after == 6
    finally:
        tmp.unlink(missing_ok=True)


def test_tuner_r3_tighten_governor():
    # Clean hotspots + no R1/R2 (need cascade with mid tier1 and high latency)
    payload = load_json(FIXTURES / "acceptance_low_t1.json")
    # Force tier1=0.5 so R1 fires with ggml... R1 would win first.
    # Use contaminated-free hotspots but make cascade skip R1/R2:
    # R1 needs ggml AND t1<0.6. If t1 is 0.7-0.9 and latency high, neither R1 nor R2.
    for i, row in enumerate(payload["per_request"]):
        row["tier_used"] = 1 if i < 7 else 2
    payload["avg_latency_ms"] = 5000.0
    tmp = FIXTURES / "_tmp_acceptance_r3.json"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    try:
        bundle = collect_bundle(
            hotspots_path=FIXTURES / "code_hotspots_apx.json",
            acceptance_path=tmp,
            governor_path=FIXTURES / "governor_overrun.json",
        )
        d = decide(bundle, PolicyState(8, 0.7, 4096))
        assert d.action == "change"
        assert d.rule_id == "R3"
        assert d.param == "governor_thinking_cap"
        assert d.after == int(4096 * 0.9)
    finally:
        tmp.unlink(missing_ok=True)


def test_tuner_one_param_and_clamp_floor():
    bundle = collect_bundle(
        hotspots_path=FIXTURES / "code_hotspots_apx.json",
        acceptance_path=FIXTURES / "acceptance_low_t1.json",
    )
    d = decide(bundle, PolicyState(2, 0.7, 4096))
    assert d.action == "hold"
    assert d.rule_id == "R1"
    assert d.before == 2
    assert d.after == 2


def test_apply_decision_only_changes_one_field():
    p = PolicyState(8, 0.7, 4096)
    d = decide(
        collect_bundle(
            hotspots_path=FIXTURES / "code_hotspots_apx.json",
            acceptance_path=FIXTURES / "acceptance_low_t1.json",
        ),
        p,
    )
    new = apply_decision(p, d)
    assert new.cascade_draft_k == 7
    assert new.tier_escalation_confidence == 0.7
    assert new.governor_thinking_cap == 4096


def test_three_dry_run_cycles_history(tmp_path: Path):
    policy_path = tmp_path / "policy_state.yaml"
    hist = tmp_path / "history.jsonl"
    save_policy(PolicyState(8, 0.7, 4096), policy_path)
    before_bytes = policy_path.read_bytes()

    metrics_text = (FIXTURES / "llama_metrics.txt").read_text(encoding="utf-8")

    # Cycle 1: R1 shrink
    r1 = run_cycle(
        dry_run=True,
        policy_path=policy_path,
        history_path=hist,
        hotspots_path=FIXTURES / "code_hotspots_apx.json",
        instruction_mix_path=FIXTURES / "instruction_mix_apx.json",
        acceptance_path=FIXTURES / "acceptance_low_t1.json",
        governor_path=FIXTURES / "governor_overrun.json",
        tier_metrics_text=metrics_text,
    )
    assert r1.outcome == "dry_run"
    assert r1.decision.rule_id == "R1"

    # Cycle 2: contaminated skip
    r2 = run_cycle(
        dry_run=True,
        policy_path=policy_path,
        history_path=hist,
        hotspots_path=FIXTURES / "code_hotspots_contaminated.json",
        acceptance_path=FIXTURES / "acceptance_low_t1.json",
        tier_metrics_text=metrics_text,
    )
    assert r2.outcome == "skipped_contaminated"

    # Cycle 3: R3 (mid tier1, high latency, governor overrun)
    payload = load_json(FIXTURES / "acceptance_low_t1.json")
    for i, row in enumerate(payload["per_request"]):
        row["tier_used"] = 1 if i < 7 else 2
    payload["avg_latency_ms"] = 5000.0
    acc = tmp_path / "acc_r3.json"
    acc.write_text(json.dumps(payload), encoding="utf-8")
    r3 = run_cycle(
        dry_run=True,
        policy_path=policy_path,
        history_path=hist,
        hotspots_path=FIXTURES / "code_hotspots_apx.json",
        acceptance_path=acc,
        governor_path=FIXTURES / "governor_overrun.json",
        tier_metrics_text=metrics_text,
    )
    assert r3.outcome == "dry_run"
    assert r3.decision.rule_id == "R3"

    rows = read_history(hist)
    assert len(rows) == 3
    assert rows[0]["outcome"] == "dry_run"
    assert rows[1]["outcome"] == "skipped_contaminated"
    assert rows[2]["rule_id"] == "R3"
    # Dry-run must not mutate policy file
    assert policy_path.read_bytes() == before_bytes


def test_live_apply_rollback_on_regression(tmp_path: Path):
    policy_path = tmp_path / "policy_state.yaml"
    hist = tmp_path / "history.jsonl"
    save_policy(PolicyState(8, 0.7, 4096), policy_path)
    restarts: list[int] = []

    def restart():
        restarts.append(1)

    before_tps = 50.0
    after_tps = 40.0  # 20% regression

    def recapture():
        # After apply, return worse throughput + same cascade shape
        return collect_bundle(
            hotspots_path=FIXTURES / "code_hotspots_apx.json",
            acceptance_path=FIXTURES / "acceptance_low_t1.json",
            tier_metrics_text=(
                f"llamacpp:predicted_tokens_seconds {after_tps}\n"
            ),
        )

    result = run_cycle(
        dry_run=False,
        policy_path=policy_path,
        history_path=hist,
        hotspots_path=FIXTURES / "code_hotspots_apx.json",
        acceptance_path=FIXTURES / "acceptance_low_t1.json",
        tier_metrics_text=f"llamacpp:predicted_tokens_seconds {before_tps}\n",
        max_regression_pct=5.0,
        env_override_path=tmp_path / "overrides.env",
        restart_fn=restart,
        recapture_fn=recapture,
        allow_demo=False,
    )
    assert result.outcome == "rolled_back"
    assert len(restarts) == 2  # apply + rollback
    # Policy restored
    from neuroswarm_arm.arop.policy_state import load_policy

    restored = load_policy(policy_path)
    assert restored.cascade_draft_k == 8
    rows = read_history(hist)
    assert rows[-1]["outcome"] == "rolled_back"
