from __future__ import annotations

<<<<<<< HEAD
from common import DEFAULT_RESULTS_DIR, evaluate_cascade, evaluate_governor, estimate_economics, evaluate_router, write_json


def main() -> None:
    router = evaluate_router()
    governor = evaluate_governor()
    cascade = evaluate_cascade()
    write_json(DEFAULT_RESULTS_DIR / "economics.json", estimate_economics(router, governor, cascade))
=======
import json
from pathlib import Path


def main() -> None:
    out = Path("work/benchmarks/economics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tokens_per_dollar": 3.5, "status": "scaffold"}, indent=2), encoding="utf-8")
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84


if __name__ == "__main__":
    main()

