#!/usr/bin/env python3
"""Show live per-tier llama-server KV cache occupancy (tiers 1/2/3).

Stdlib-only entrypoint: loads kv_cache_status module directly without pulling
in neuroswarm_arm.runtime.dipa (which requires gateway deps like anyio).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import types
from pathlib import Path


def _load_kv_cache_api():
    """Import kv_cache_status + slot_client without neuroswarm_arm package init."""
    root = Path(__file__).resolve().parents[1]
    base = root / "neuroswarm_arm" / "runtime" / "dipa" / "backends" / "llama_cpp"
    pkg_name = "neuroswarm_arm.runtime.dipa.backends.llama_cpp"

    slot_path = base / "slot_client.py"
    kv_path = base / "kv_cache_status.py"

    if not slot_path.is_file() or not kv_path.is_file():
        raise FileNotFoundError(
            f"Missing {slot_path} or {kv_path}. Run from repo root after git pull."
        )

    # Fake package so relative import in kv_cache_status works.
    if pkg_name not in sys.modules:
        sys.modules[pkg_name] = types.ModuleType(pkg_name)

    sc_spec = importlib.util.spec_from_file_location(f"{pkg_name}.slot_client", slot_path)
    if sc_spec is None or sc_spec.loader is None:
        raise ImportError(f"cannot load {slot_path}")
    sc_mod = importlib.util.module_from_spec(sc_spec)
    sys.modules[f"{pkg_name}.slot_client"] = sc_mod
    sc_spec.loader.exec_module(sc_mod)

    kv_spec = importlib.util.spec_from_file_location(f"{pkg_name}.kv_cache_status", kv_path)
    if kv_spec is None or kv_spec.loader is None:
        raise ImportError(f"cannot load {kv_path}")
    kv_mod = importlib.util.module_from_spec(kv_spec)
    kv_mod.__package__ = pkg_name
    sys.modules[f"{pkg_name}.kv_cache_status"] = kv_mod
    kv_spec.loader.exec_module(kv_mod)
    return kv_mod


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

    try:
        kv = _load_kv_cache_api()
    except (FileNotFoundError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    fetch_tier = kv.fetch_tier_kv_cache_status
    fetch_all = kv.fetch_all_tier_kv_cache_status
    format_table = kv.format_tier_table

    tiers = [1, 2, 3] if args.tier == "all" else [int(args.tier)]

    def _run_once() -> list:
        if len(tiers) == 1:
            return [fetch_tier(tiers[0], timeout_s=args.timeout)]
        return fetch_all(tiers, timeout_s=args.timeout)

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
            print(format_table(statuses), end="")

        if not args.watch:
            break
        time.sleep(max(0.5, float(args.watch)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
