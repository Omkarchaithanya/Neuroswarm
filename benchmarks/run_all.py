from __future__ import annotations

import argparse
import json
from pathlib import Path
import time


def write_result(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="work/benchmarks/run_all.json")
    args = parser.parse_args()
    start = time.time()
    payload = {
        "status": "scaffold",
        "elapsed_ms": round((time.time() - start) * 1000, 2),
        "notes": "Replace with VM-backed benchmarks.",
    }
    write_result(Path(args.out), payload)


if __name__ == "__main__":
    main()

