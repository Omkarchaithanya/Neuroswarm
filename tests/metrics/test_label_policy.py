"""Label allowlist / metric-def override behavior."""

from neuroswarm_arm.metrics.labels import LabelPolicy


def test_metric_def_label_keys_override_global_allowlist():
    policy = LabelPolicy()
    # function is now in ALLOWED_LABELS; also permitted via metric-def keys
    out = policy.normalize({"function": "llama_decode", "bogus": "x"}, allowed_keys=("function",))
    assert out == {"function": "llama_decode"}


def test_event_label_for_pmu():
    policy = LabelPolicy()
    out = policy.normalize({"event": "cycles"}, allowed_keys=("event",))
    assert out == {"event": "cycles"}


def test_forbidden_still_dropped_even_if_in_permit():
    policy = LabelPolicy()
    out = policy.normalize({"user_id": "u1", "function": "f"}, allowed_keys=("function", "user_id"))
    assert "user_id" not in out
    assert out.get("function") == "f"
