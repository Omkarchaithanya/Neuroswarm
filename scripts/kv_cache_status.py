#!/usr/bin/env python3
"""Show live per-tier llama-server KV cache occupancy (tiers 1/2/3)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.kv_cache_status import (
    fetch_all_tier_kv_cache_status,
    fetch_tier_kv_cache_status,
    format_tier_table,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report live KV cache tokens per llama-server tier (8081/8082/8083)",
    )
    parser.add_argument(
        "--tier",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Which tier to query (default: all)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of table")
    parser.add_argument(
        "--watch",
        type=float,
        metavar="SECONDS",
        help="Refresh every N seconds (Ctrl+C to stop)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout per tier (default: 15)",
    )
    args = parser.parse_args()

    tiers = [1, 2, 3] if args.tier == "all" else [int(args.tier)]

    def _run_once() -> list:
        if len(tiers) == 1:
            return [fetch_tier_kv_cache_status(tiers[0], timeout_s=args.timeout)]
        return fetch_all_tier_kv_cache_status(tiers, timeout_s=args.timeout)

    while True:
        statuses = _run_once()
        if args.json:
            payload = {
                "tiers": [s.to_dict() for s in statuses],
                "ts": time.time(),
            }
            print(json.dumps(payload, indent=2))
        else:
            if args.watch:
                print(f"\n--- KV cache @ {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
            print(format_tier_table(statuses), end="")

        if not args.watch:
            break
        time.sleep(max(0.5, float(args.watch)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
