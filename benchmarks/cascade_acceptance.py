from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    out = Path("work/benchmarks/cascade_acceptance.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"acceptance_rate": 0.7, "status": "scaffold"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

