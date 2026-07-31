"""DraftModelRegistry pairing tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.proposal.draft_registry import DraftModelRegistry


def test_resolve_llama_neoverse_v2():
    reg = DraftModelRegistry()
    assert reg.resolve("Llama-3.2-3B-Instruct-4bit", "neoverse-v2") == (
        "Llama-3.2-1B-Instruct-4bit",
        "Q4_0",
    )


def test_resolve_unknown_returns_none():
    reg = DraftModelRegistry()
    assert reg.resolve("Unknown-Model", "neoverse-v2") is None


def test_resolve_llama_apple_m():
    reg = DraftModelRegistry()
    assert reg.resolve("Llama-3.2-3B-Instruct-4bit", "apple-m") == (
        "Llama-3.2-1B-Instruct-4bit",
        "Q4_0",
    )
