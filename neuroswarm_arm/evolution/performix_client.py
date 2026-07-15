from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess


@dataclass(slots=True)
class PerformixClient:
    binary: str = "apx"

    def run_recipe(self, recipe: str, output: Path, target: str | None = None, binary: str | None = None, duration: int | None = None) -> dict:
        cmd = [self.binary, "recipe", "run", recipe, "--output", str(output)]
        if target:
            cmd.extend(["--target", target])
        if binary:
            cmd.extend(["--binary", binary])
        if duration is not None:
            cmd.extend(["--duration", str(duration)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output": str(output),
        }

    def compare(self, baseline: Path, optimized: Path, output: Path) -> dict:
        cmd = [self.binary, "recipe", "compare", "--baseline", str(baseline), "--optimized", str(optimized), "--output", str(output)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

