"""Tests for MLX backend (Apple Silicon M3/M4/M5)."""

from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_SKIP_REASON = "MLX backend requires macOS with mlx-lm installed"
_SKIP = pytest.mark.skipif(
    sys.platform != "darwin" or importlib.util.find_spec("mlx") is None,
    reason=_SKIP_REASON,
)
_E2E = pytest.mark.skipif(
    os.getenv("NSA_MLX_E2E", "0") != "1",
    reason="Set NSA_MLX_E2E=1 with models on disk for slow e2e",
)


# ---------------------------------------------------------------------------
# Test 1: Backend can be instantiated (unit test, no model required)
# ---------------------------------------------------------------------------
@_SKIP
def test_mlx_backend_instantiation() -> None:
    from neuroswarm_arm.runtime.dipa.backends.mlx.backend import MlxBackend

    backend = MlxBackend(name="mlx_test", base_url="http://127.0.0.1:9999")
    assert backend.name == "mlx_test"
    assert backend.base_url == "http://127.0.0.1:9999"
    assert backend.capabilities.speculation is True
    assert backend.capabilities.self_speculation is True
    assert backend.capabilities.streaming is True
    assert "gpu" in [dc.value for dc in backend.capabilities.device_classes]


# ---------------------------------------------------------------------------
# Test 2: Health check returns HEALTHY when the model exists (mocked)
# ---------------------------------------------------------------------------
@_SKIP
@pytest.mark.asyncio
async def test_mlx_health_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_MLX_MODEL_PATH", "/fake/model")
    from neuroswarm_arm.runtime.dipa.backends.mlx.backend import MlxBackend

    backend = MlxBackend(name="mlx", base_url="http://127.0.0.1:9999")
    with patch.object(backend, "_probe_load_model", return_value=True):
        status = await backend.health()
    assert status.state.value == "healthy"
    assert "MLX model loaded" in status.message
    assert status.details["model_path"] == "/fake/model"
    assert status.details["health_probe"] == "load_model"


@_SKIP
@pytest.mark.asyncio
async def test_mlx_health_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_MLX_MODEL_PATH", "/fake/model")
    from neuroswarm_arm.runtime.dipa.backends.mlx.backend import MlxBackend

    backend = MlxBackend(name="mlx", base_url="http://127.0.0.1:9999")
    with patch.object(backend, "_probe_load_model", return_value=False):
        status = await backend.health()
    assert status.state.value == "unhealthy"
    assert "MLX model load failed" in status.message


@_SKIP
@pytest.mark.asyncio
async def test_mlx_generate_inprocess_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_MLX_MODEL_PATH", "/fake/model")
    from neuroswarm_arm.runtime.dipa.backends.mlx.backend import MlxBackend
    from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
    from neuroswarm_arm.runtime.dipa.interfaces.types import (
        GenerateRequest,
        InferenceRequest,
    )

    backend = MlxBackend(name="mlx", base_url="http://127.0.0.1:9999")
    fake = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    with patch.object(backend, "_generate_inprocess_sync", return_value=fake):
        req = GenerateRequest(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=8,
            temperature=0.0,
        )
        ctx = ExecutionContext(
            request=InferenceRequest(
                messages=[{"role": "user", "content": "hi"}],
            ),
        )
        result = await backend.generate(req, ctx)
    assert result.text == "hello"
    assert result.metrics.get("speculation") == 0.0


@_SKIP
@pytest.mark.asyncio
async def test_mlx_spec_acceptance_rate_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NSA_MLX_MODEL_PATH", "/fake/model")
    monkeypatch.setenv("NSA_MLX_DRAFT_MODEL_PATH", "/fake/draft")
    monkeypatch.setenv("NSA_MLX_NUM_DRAFT_TOKENS", "5")
    from neuroswarm_arm.runtime.dipa.backends.mlx.backend import MlxBackend
    from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
    from neuroswarm_arm.runtime.dipa.interfaces.types import (
        GenerateRequest,
        InferenceRequest,
    )

    backend = MlxBackend(name="mlx", base_url="http://127.0.0.1:9999")
    fake_raw = {
        "choices": [{"message": {"content": "spec poem about ARM"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        "acceptance_rate": 0.72,
    }
    mock_spec = MagicMock()
    mock_spec.propose_sync.return_value = fake_raw
    with patch.object(backend, "_ensure_spec_controller", return_value=mock_spec):
        req = GenerateRequest(
            messages=[{"role": "user", "content": "Write a short poem about ARM CPUs."}],
            max_tokens=64,
            temperature=0.2,
            speculative=True,
        )
        ctx = ExecutionContext(
            request=InferenceRequest(
                messages=[
                    {"role": "user", "content": "Write a short poem about ARM CPUs."}
                ],
            ),
        )
        result = await backend.generate(req, ctx)
    assert len(result.text.strip()) > 0
    assert result.metrics.get("ascr_acceptance_rate", 0.0) > 0.5
    assert result.metrics.get("speculation") == 1.0


# ---------------------------------------------------------------------------
# Test 3 (slow): End-to-end chat returns non-empty text
# ---------------------------------------------------------------------------
@_SKIP
@_E2E
@pytest.mark.slow
@pytest.mark.asyncio
async def test_mlx_e2e_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_MLX_MODEL_PATH", "/models/mlx/llama-3.2-3b-instruct-4bit")
    from neuroswarm_arm.runtime.dipa.backends.mlx.backend import MlxBackend
    from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
    from neuroswarm_arm.runtime.dipa.interfaces.types import (
        GenerateRequest,
        InferenceRequest,
    )

    backend = MlxBackend(name="mlx", base_url="http://127.0.0.1:8080")
    req = GenerateRequest(
        messages=[{"role": "user", "content": "Reply with exactly: hello"}],
        max_tokens=16,
        temperature=0.0,
    )
    ctx = ExecutionContext(
        request=InferenceRequest(
            messages=[{"role": "user", "content": "Reply with exactly: hello"}],
        ),
    )
    result = await backend.generate(req, ctx)
    assert len(result.text.strip()) > 0
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.latency_ms > 0.0


# ---------------------------------------------------------------------------
# Test 4 (slow): Spec mode produces ascr_acceptance_rate > 0.5
# ---------------------------------------------------------------------------
@_SKIP
@_E2E
@pytest.mark.slow
@pytest.mark.asyncio
async def test_mlx_spec_acceptance_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_MLX_MODEL_PATH", "/models/mlx/llama-3.2-3b-instruct-4bit")
    monkeypatch.setenv(
        "NSA_MLX_DRAFT_MODEL_PATH", "/models/mlx/llama-3.2-1b-instruct-4bit"
    )
    monkeypatch.setenv("NSA_MLX_NUM_DRAFT_TOKENS", "5")
    from neuroswarm_arm.runtime.dipa.backends.mlx.backend import MlxBackend
    from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
    from neuroswarm_arm.runtime.dipa.interfaces.types import (
        GenerateRequest,
        InferenceRequest,
    )

    backend = MlxBackend(name="mlx", base_url="http://127.0.0.1:8080")
    req = GenerateRequest(
        messages=[{"role": "user", "content": "Write a short poem about ARM CPUs."}],
        max_tokens=64,
        temperature=0.2,
        speculative=True,
    )
    ctx = ExecutionContext(
        request=InferenceRequest(
            messages=[{"role": "user", "content": "Write a short poem about ARM CPUs."}],
        ),
    )
    result = await backend.generate(req, ctx)
    assert len(result.text.strip()) > 0
    assert result.latency_ms > 0.0
    assert float(result.metrics.get("ascr_acceptance_rate", 0.0)) > 0.5
