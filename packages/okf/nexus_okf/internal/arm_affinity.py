from __future__ import annotations

import os
from typing import Iterable


def pin_workers(cores: Iterable[int] | None = None) -> list[int]:
    if cores is None:
        n = os.cpu_count() or 4
        cores = list(range(min(n, 8)))
    cores = list(cores)
    try:
        os.sched_setaffinity(0, set(cores))
    except (AttributeError, OSError, PermissionError):
        pass
    return cores


def worker_count(default_cap: int = 8) -> int:
    return max(1, min(os.cpu_count() or 2, default_cap))
