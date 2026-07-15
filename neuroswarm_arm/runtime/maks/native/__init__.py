"""Native ARM feature stubs — MTE / NUMA / compression hooks."""

from __future__ import annotations

AVAILABLE = False  # Axion: MTE/CXL unavailable


def feature_matrix() -> dict[str, bool]:
    from .mte import AVAILABLE as mte_ok
    from .numa import AVAILABLE as numa_ok
    from .compression import AVAILABLE as comp_ok

    return {"mte": mte_ok, "numa": numa_ok, "native_compression": comp_ok}
