"""build_routed_inference_hints tool_search activation + pass_through snapshot."""

from __future__ import annotations

from types import SimpleNamespace

from neuroswarm_arm.runtime.router.orchestration import build_routed_inference_hints
from neuroswarm_arm.runtime.router.tool_search import BRIDGE_TOOL_SCHEMA, ToolSearchConfig
from neuroswarm_arm.runtime.router.models import ToolRecord


class _FakeRoutingResult:
    def __init__(self) -> None:
        tool = SimpleNamespace(name="s3_presign_url", id="s3.presign_url")
        scored = SimpleNamespace(tool=tool, score=0.91, confidence=0.91)
        self.tools = [scored]
        self.top_k = 3
        self.confidence_top1 = 0.91
        self.high_confidence = True
        self.prompt_tokens_before = 100
        self.prompt_tokens_after = 20
        self.query = "presign"
        self.candidate_count = 1


def _fat_registry(n: int = 40) -> list[ToolRecord]:
    return [
        ToolRecord(
            id=f"aws.tool_{i}",
            name=f"tool_{i}",
            description=f"desc {i} " + ("x" * 200),
            namespace="aws",
            input_schema={"type": "object", "properties": {f"p{j}": {"type": "string"} for j in range(8)}},
        )
        for i in range(n)
    ]


def test_pass_through_byte_identical_when_cfg_none() -> None:
    result = _FakeRoutingResult()
    schemas = [{"type": "function", "function": {"name": "s3_presign_url"}}]
    prompt = "TOOLS:\ns3_presign_url"
    a = build_routed_inference_hints("q", result, prompt_block=prompt, schemas=schemas)  # type: ignore[arg-type]
    b = build_routed_inference_hints(
        "q",
        result,  # type: ignore[arg-type]
        prompt_block=prompt,
        schemas=schemas,
        tool_search_cfg=None,
    )
    assert a.tool_schemas == b.tool_schemas
    assert a.tool_prompt_block == b.tool_prompt_block
    assert a.tool_search_mode == "pass_through"
    assert a.as_dict()["tool_search_mode"] == "pass_through"


def test_enabled_off_snapshot_matches_no_cfg() -> None:
    result = _FakeRoutingResult()
    schemas = [{"type": "function", "function": {"name": "s3_presign_url"}}]
    prompt = "TOOLS:\ns3_presign_url"
    baseline = build_routed_inference_hints("q", result, prompt_block=prompt, schemas=schemas)  # type: ignore[arg-type]
    off = build_routed_inference_hints(
        "q",
        result,  # type: ignore[arg-type]
        prompt_block=prompt,
        schemas=schemas,
        tool_search_cfg=ToolSearchConfig(enabled="off"),
        registry=_fat_registry(),
        context_length=1000,
    )
    assert off.tool_schemas == baseline.tool_schemas
    assert off.tool_prompt_block == baseline.tool_prompt_block
    assert off.tool_search_mode == "pass_through"


def test_bridge_mode_replaces_schemas_with_bridge_only() -> None:
    result = _FakeRoutingResult()
    schemas = [{"type": "function", "function": {"name": "s3_presign_url"}}]
    hints = build_routed_inference_hints(
        "q",
        result,  # type: ignore[arg-type]
        prompt_block="TOOLS:\ns3_presign_url",
        schemas=schemas,
        tool_search_cfg=ToolSearchConfig(enabled="on", listing="auto", listing_max_tokens=20000),
        registry=_fat_registry(20),
        context_length=1000,
    )
    assert hints.tool_search_mode == "bridge"
    assert hints.tool_schemas == [BRIDGE_TOOL_SCHEMA]
    assert len(hints.tool_schemas) == 1
    assert "<tool_listing>" in hints.tool_prompt_block
    assert "s3_presign_url" not in str(hints.tool_schemas[0].get("function", {}).get("name", "")) or \
        hints.tool_schemas[0]["function"]["name"] == "tool_search"
    # Must not contain deferrable full schemas
    assert all(
        (s.get("function") or {}).get("name") == "tool_search" for s in hints.tool_schemas
    )
