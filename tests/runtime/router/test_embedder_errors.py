"""Router embedder + TurboVec health regressions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from neuroswarm_arm.runtime.router.embedding_service import EmbeddingService
from neuroswarm_arm.runtime.router.health import build_health_report
from neuroswarm_arm.runtime.router.models import EmbeddingSpec
from neuroswarm_arm.runtime.router.router_exceptions import EmbeddingError
from neuroswarm_arm.runtime.router.turbovec_index import TurboVecIndex


def test_missing_embedder_raises_loud() -> None:
    spec = EmbeddingSpec(model_name="missing-model", use_onnx=True, onnx_path="/no/such/model.onnx")
    svc = EmbeddingService(spec)
    svc._onnx = MagicMock()  # noqa: SLF001
    svc._tokenizer = MagicMock(side_effect=RuntimeError("tokenizer missing"))
    with pytest.raises(EmbeddingError):
        svc._encode_onnx("hello")  # noqa: SLF001


def test_turbovec_health_reports_real_backend() -> None:
    index = TurboVecIndex(dims=8, bit_width=4)
    index.insert("t1", np.array([0.1] * 8, dtype=np.float32))
    runtime = SimpleNamespace(
        config=SimpleNamespace(
            encoder_name="test",
            top_k=3,
            threshold=0.0,
            enable_hot_reload=False,
            snapshot_dir=Path("."),
        ),
        index=index,
        embedder=EmbeddingService(EmbeddingSpec(model_name="hash-test")),
        registry=SimpleNamespace(size=lambda: 1),
        arm_features=SimpleNamespace(
            arch="aarch64",
            is_arm64=True,
            neon=True,
            sve2=False,
            numa_nodes=1,
        ),
    )
    report = build_health_report(runtime)
    assert report["ann_backend"] in {"turbovec", "turbovec+exact", "numpy"}
    assert report["kernel_path"] in {"turbovec", "turbovec+exact", "numpy", "exact"}
