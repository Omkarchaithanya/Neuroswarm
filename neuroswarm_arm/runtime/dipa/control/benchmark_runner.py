"""BenchmarkRunner — thin control-plane harness for llama-bench / cascade."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping


class BenchmarkRunner:
    def __init__(self) -> None:
        self._last: dict[str, Any] = {}

    def run(
        self,
        name: str,
        fn: Callable[[], Any],
        *,
        iterations: int = 1,
    ) -> Mapping[str, Any]:
        times: list[float] = []
        result: Any = None
        for _ in range(max(1, iterations)):
            t0 = time.perf_counter()
            result = fn()
            times.append((time.perf_counter() - t0) * 1000.0)
        payload = {
            "name": name,
            "iterations": iterations,
            "latency_ms_avg": sum(times) / len(times),
            "latency_ms_min": min(times),
            "latency_ms_max": max(times),
            "result": result if _is_jsonish(result) else str(type(result)),
        }
        self._last = payload
        return payload

    def last(self) -> Mapping[str, Any]:
        return dict(self._last)


def _is_jsonish(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, dict, list, type(None)))
