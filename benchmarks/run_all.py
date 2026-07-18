from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    evaluate_cascade,
    evaluate_governor,
    evaluate_router,
    estimate_economics,
    system_snapshot,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="work/benchmarks/run_all.json")
    args = parser.parse_args()
    out = Path(args.out)
    snapshot = system_snapshot()
    router = evaluate_router()
    governor = evaluate_governor()
    cascade = evaluate_cascade()
    economics = estimate_economics(router, governor, cascade)
    payload = {
        "status": "ok",
        "system": snapshot,
        "router_accuracy": router,
        "governor_tokens": governor,
        "cascade_acceptance": cascade,
        "economics": economics,
    }
    write_json(out, payload)


if __name__ == "__main__":
    main()

