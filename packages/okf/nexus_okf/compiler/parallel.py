from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from nexus_okf.internal.arm_affinity import worker_count


def parallel_map(fn: Callable, items: list, workers: int | None = None) -> list:
    if not items:
        return []
    n = workers or worker_count()
    if n <= 1 or len(items) < 4:
        return [fn(x) for x in items]
    out = []
    with ProcessPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(fn, x) for x in items]
        for f in as_completed(futs):
            out.append(f.result())
    return out


def shard_paths(paths: list[Path], shards: int) -> list[list[Path]]:
    shards = max(1, shards)
    buckets: list[list[Path]] = [[] for _ in range(shards)]
    for i, p in enumerate(paths):
        buckets[i % shards].append(p)
    return buckets
