<<<<<<< HEAD
"""Backward-compatible EvolutionLoop — delegates to RuntimeOptimizer when available."""

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from .performix_client import PerformixClient


@dataclass
class EvolutionLoop:
<<<<<<< HEAD
    """Legacy hourly Performix hotspots loop.

    Prefer ``build_arop(...).run_once()`` for the full AROP pipeline.
    """

=======
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
    performix: PerformixClient
    output_dir: Path
    enabled: bool = True
    interval_seconds: int = 3600
<<<<<<< HEAD
    optimizer: object | None = None

    def run_once(self, binary: str) -> dict:
        if self.optimizer is not None and hasattr(self.optimizer, "run_once"):
            result = self.optimizer.run_once()
            return {
                "arop": True,
                "status": getattr(result, "status", "ok"),
                "policy_id": getattr(result, "policy_id", None),
                "message": getattr(result, "message", ""),
            }
=======

    def run_once(self, binary: str) -> dict:
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
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
<<<<<<< HEAD
=======

>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
