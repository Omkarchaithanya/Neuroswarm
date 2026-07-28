"""Native ARM feature stubs — MTE / NUMA / compression hooks."""

from __future__ import annotations

from .mte import AVAILABLE as _mte_available

AVAILABLE = _mte_available


def feature_matrix() -> dict[str, bool]:
    from .compression import AVAILABLE as comp_ok
    from .mte import AVAILABLE as mte_ok
    from .numa import AVAILABLE as numa_ok

    return {"mte": mte_ok, "numa": numa_ok, "native_compression": comp_ok}
