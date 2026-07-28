#!/usr/bin/env python3
"""Unit tests for llama-server content extraction (reasoning models)."""

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import (
    _extract_chat_content,
    _parse_sse_line,
)


def test_extract_prefers_content_over_reasoning() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "LAYER-OK",
                    "reasoning_content": "thinking...",
                }
            }
        ]
    }
    assert _extract_chat_content(payload) == "LAYER-OK"


def test_extract_falls_back_to_reasoning_content() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "I should reply LAYER-OK",
                }
            }
        ]
    }
    assert _extract_chat_content(payload) == "I should reply LAYER-OK"


def test_parse_sse_reasoning_delta() -> None:
    line = 'data: {"choices":[{"delta":{"reasoning_content":"think"}}]}'
    assert _parse_sse_line(line) == ["think"]


def test_parse_sse_content_preferred() -> None:
    line = 'data: {"choices":[{"delta":{"content":"hi","reasoning_content":"x"}}]}'
    assert _parse_sse_line(line) == ["hi"]
