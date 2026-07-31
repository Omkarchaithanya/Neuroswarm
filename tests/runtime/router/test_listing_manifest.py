"""Listing manifest truncation + footer."""

from __future__ import annotations

from neuroswarm_arm.runtime.router.models import ToolRecord
from neuroswarm_arm.runtime.router.tool_search import build_listing_manifest
from neuroswarm_arm.runtime.router.tool_schema_builder import estimate_schema_tokens


def test_listing_truncation_footer_and_budget() -> None:
    tools = [
        ToolRecord(
            id=f"aws.tool_{i}",
            name=f"tool_{i}",
            description=("Generate a presigned URL for upload/download. " * 5),
            namespace="aws-mcp",
        )
        for i in range(80)
    ]
    max_tokens = 200
    manifest, truncated = build_listing_manifest(tools, max_tokens)
    assert truncated is True
    assert "<tool_listing>" in manifest
    assert "</tool_listing>" in manifest
    assert "more tools; call tool_search" in manifest
    assert estimate_schema_tokens({"manifest": manifest}) <= max_tokens


def test_listing_no_truncation_when_budget_large() -> None:
    tools = [
        ToolRecord(id="aws.a", name="a", description="short", namespace="aws"),
        ToolRecord(id="gh.b", name="b", description="short", namespace="github"),
    ]
    manifest, truncated = build_listing_manifest(tools, 20000)
    assert truncated is False
    assert "server: aws" in manifest
    assert "server: github" in manifest
    assert "more tools" not in manifest
