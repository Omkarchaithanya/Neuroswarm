from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class MetricsStore:
    lock: Lock = field(default_factory=Lock)
    counters: dict[str, float] = field(default_factory=dict)

    def inc(self, name: str, value: float = 1.0) -> None:
        with self.lock:
            self.counters[name] = self.counters.get(name, 0.0) + value

    def set(self, name: str, value: float) -> None:
        with self.lock:
            self.counters[name] = value

    def export_prometheus(self) -> str:
        with self.lock:
            lines = []
            for key, value in sorted(self.counters.items()):
                lines.append(f"# TYPE {key} gauge")
                lines.append(f"{key} {value}")
            return "\n".join(lines) + "\n"


metrics = MetricsStore()

