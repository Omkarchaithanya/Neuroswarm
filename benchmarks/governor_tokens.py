from __future__ import annotations

<<<<<<< HEAD
from common import DEFAULT_RESULTS_DIR, evaluate_governor, write_json


def main() -> None:
    write_json(DEFAULT_RESULTS_DIR / "governor_tokens.json", evaluate_governor())
=======
import json
from pathlib import Path


def main() -> None:
    out = Path("work/benchmarks/governor_tokens.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"baseline": 5000, "governed": 2000, "status": "scaffold"}, indent=2), encoding="utf-8")
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84


if __name__ == "__main__":
    main()

