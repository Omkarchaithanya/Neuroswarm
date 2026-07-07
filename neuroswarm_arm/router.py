from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Callable, Any


@dataclass
class HAOEScheduler:
    fast_cores: list[int] = field(default_factory=lambda: list(range(4)))
    slow_cores: list[int] = field(default_factory=lambda: list(range(4, 16)))
    queues: dict[int, deque] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.queues:
            self.queues = {core: deque() for core in self.fast_cores + self.slow_cores}

    def schedule(self, task: Callable[..., Any], priority: str = "normal", *args: Any, **kwargs: Any) -> Any:
        _ = self.fast_cores if priority == "critical" else self.slow_cores
        return task(*args, **kwargs)

