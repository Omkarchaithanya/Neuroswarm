"""Hermes tool_search: BRIDGE_TOOL_SCHEMA, response shape, decide_mode truth table."""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from neuroswarm_arm.runtime.router.tool_search import (
    BRIDGE_TOOL_SCHEMA,
    ToolSearchConfig,
    build_bridge_response,
    decide_mode,
)


def test_bridge_tool_schema_name_and_required() -> None:
    assert BRIDGE_TOOL_SCHEMA["type"] == "function"
    fn = BRIDGE_TOOL_SCHEMA["function"]
    assert fn["name"] == "tool_search"
    assert fn["parameters"]["required"] == ["query"]
    assert fn["parameters"]["additionalProperties"] is False
    assert "limit" in fn["parameters"]["properties"]
    assert "scope" in fn["parameters"]["properties"]


def test_build_bridge_response_shape_and_truncate() -> None:
    tools = [
        SimpleNamespace(id=f"t{i}", name=f"n{i}", description=f"d{i}", namespace="aws")
        for i in range(7)
    ]
    out = build_bridge_response("presign", tools, limit=5)
    assert out["mode"] == "tool_search"
    assert out["query"] == "presign"
    assert out["limit"] == 5
    assert len(out["results"]) == 5
    assert out["truncated"] is True
    assert out["results"][0]["id"] == "t0"
    assert "name" in out["results"][0]
    assert "description" in out["results"][0]


def test_build_bridge_response_not_truncated() -> None:
    tools = [SimpleNamespace(id="a", name="a", description="x", namespace="")]
    out = build_bridge_response("q", tools, limit=5)
    assert out["truncated"] is False
    assert len(out["results"]) == 1


@pytest.mark.parametrize(
    "enabled,has_deferrable,share_above,expected",
    [
        ("off", True, True, "pass_through"),
        ("off", True, False, "pass_through"),
        ("off", False, True, "pass_through"),
        ("on", True, True, "bridge"),
        ("on", True, False, "bridge"),
        ("on", False, True, "pass_through"),
        ("auto", True, True, "bridge"),
        ("auto", True, False, "pass_through"),
        ("auto", False, True, "bridge"),  # share alone gates auto; deferred_tokens drive share
    ],
)
def test_decide_mode_nine_cell(
    enabled: str, has_deferrable: bool, share_above: bool, expected: str
) -> None:
    threshold = 10.0
    context_length = 1000
    deferred = 200 if share_above else 50  # 20% vs 5%
    # When has_deferrable is False but share_above for auto, still pass deferred tokens —
    # formula for auto ignores has_deferrable; on requires it.
    if not has_deferrable and enabled == "on":
        deferred = 0
    mode = decide_mode(
        enabled=enabled,
        threshold_pct=threshold,
        context_length=context_length,
        deferred_schema_tokens=deferred if (has_deferrable or enabled == "auto") else 0,
        has_deferrable=has_deferrable,
    )
    assert mode == expected


def test_tool_search_config_defaults() -> None:
    cfg = ToolSearchConfig()
    assert cfg.enabled == "auto"
    assert cfg.threshold_pct == 10.0
    assert cfg.search_default_limit == 5
    assert cfg.max_search_limit == 20
    assert cfg.listing == "auto"
    assert cfg.listing_max_tokens == 20000


def test_tool_search_config_rejects_bad_threshold() -> None:
    with pytest.raises(ValueError):
        ToolSearchConfig(threshold_pct=101)
