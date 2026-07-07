from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    out = Path("work/benchmarks/economics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tokens_per_dollar": 3.5, "status": "scaffold"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

