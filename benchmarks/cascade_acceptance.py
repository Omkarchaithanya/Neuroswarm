from __future__ import annotations

<<<<<<< HEAD
from common import DEFAULT_RESULTS_DIR, evaluate_cascade, write_json


def main() -> None:
    write_json(DEFAULT_RESULTS_DIR / "cascade_acceptance.json", evaluate_cascade())
=======
import json
from pathlib import Path


def main() -> None:
    out = Path("work/benchmarks/cascade_acceptance.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"acceptance_rate": 0.7, "status": "scaffold"}, indent=2), encoding="utf-8")
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84


if __name__ == "__main__":
    main()

