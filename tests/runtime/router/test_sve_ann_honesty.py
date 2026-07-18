"""ANN backend honesty + SveDot stub tests."""

from __future__ import annotations

import numpy as np

from neuroswarm_arm.runtime.router.backends.registry import build_vector_index, kernel_path_for
from neuroswarm_arm.runtime.router.backends.sve_dot import SveDotIndex
from neuroswarm_arm.runtime.router.models import MetricKind


def test_sve_dot_delegates_to_numpy_and_is_honest() -> None:
    idx = SveDotIndex(4, metric=MetricKind.COSINE)
    assert idx.backend_name == "sve_dot"
    assert idx.kernel_path == "numpy_stub"
    assert idx.sve_kernels_active is False
    v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    idx.insert("a", v)
    hits = idx.search(v, 1)
    assert hits and hits[0].key == "a"


def test_build_vector_index_sve_and_exact() -> None:
    sve = build_vector_index("sve_dot", 8)
    exact = build_vector_index("exact", 8)
    assert kernel_path_for(sve) == "numpy_stub"
    assert kernel_path_for(exact) == "numpy"
    assert getattr(sve, "sve_kernels_active", True) is False
