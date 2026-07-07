from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from .performix_client import PerformixClient


@dataclass
class EvolutionLoop:
    performix: PerformixClient
    output_dir: Path
    enabled: bool = True
    interval_seconds: int = 3600

    def run_once(self, binary: str) -> dict:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        hotspots = self.performix.run_recipe(
            "code-hotspots",
            output=self.output_dir / "hotspots.json",
            binary=binary,
            duration=60,
        )
        return hotspots

    def run_forever(self, binary: str) -> None:
        while self.enabled:
            self.run_once(binary)
            time.sleep(self.interval_seconds)

