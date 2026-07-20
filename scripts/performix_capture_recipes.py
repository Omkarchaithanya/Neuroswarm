#!/usr/bin/env python3
"""Capture Arm Performix GA recipes via PerformixClient (correct apx flow)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neuroswarm_arm.evolution.performix_client import (  # noqa: E402
    GA_RECIPE_IDS,
    PerformixClient,
    normalize_recipe,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="benchmarks/results/performix")
    parser.add_argument("--pub-dir", default="docs/evidence/performix")
    parser.add_argument("--duration", type=int, default=int(os.getenv("PERFORMIX_DURATION", "60")))
    parser.add_argument("--target", default=os.getenv("ARM_PERFORMIX_TARGET") or os.getenv("PERFORMIX_TARGET") or "")
    parser.add_argument("--binary", default=os.getenv("NSA_BENCH_BINARY") or "")
    parser.add_argument("--list-only", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    pub_dir = Path(args.pub_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pub_dir.mkdir(parents=True, exist_ok=True)

    list_path = out_dir / "00-recipe-list.txt"
    try:
        listed = subprocess.run(
            [os.getenv("NSA_AROP_PERFORMIX_BIN", "apx"), "recipe", "list"],
            capture_output=True,
            text=True,
            check=False,
        )
        list_path.write_text((listed.stdout or "") + (listed.stderr or ""), encoding="utf-8")
        shutil.copy2(list_path, pub_dir / list_path.name)
        print(list_path.read_text(encoding="utf-8")[:4000])
    except FileNotFoundError:
        list_path.write_text("apx not found on PATH\n", encoding="utf-8")
        print("apx not found", file=sys.stderr)
        return 2

    if args.list_only:
        return 0

    client = PerformixClient(binary=os.getenv("NSA_AROP_PERFORMIX_BIN", "apx"))
    target = args.target.strip() or None
    binary = args.binary.strip() or None
    failures: list[str] = []

    # instruction_mix / cpu_microarchitecture need --workload (not --system-wide).
    NEED_WORKLOAD = {"instruction_mix", "cpu_microarchitecture", "memory_access"}

    for i, recipe in enumerate(GA_RECIPE_IDS, start=1):
        rid = normalize_recipe(recipe)
        out = out_dir / f"{i:02d}-{rid}.json"
        use_binary = binary
        system_wide = True
        if rid in NEED_WORKLOAD:
            if not use_binary:
                print(f"SKIP {rid}: set NSA_BENCH_BINARY / --binary (apx requires --workload)", file=sys.stderr)
                failures.append(rid)
                continue
            system_wide = False
        print(f"==> {rid} → {out}")
        payload = client.run_recipe(
            rid,
            out,
            target=target,
            binary=use_binary,
            duration=args.duration,
            system_wide=system_wide,
        )
        meta = {
            "recipe": rid,
            "returncode": payload.get("returncode"),
            "run_id": payload.get("run_id"),
            "extracted": payload.get("extracted"),
            "cmd": payload.get("cmd"),
        }
        meta_path = out.with_suffix(out.suffix + ".meta.json")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        if out.is_file():
            shutil.copy2(out, pub_dir / out.name)
            shutil.copy2(meta_path, pub_dir / meta_path.name)
            print(f"OK {rid}")
        else:
            failures.append(rid)
            print(f"FAIL {rid}: {payload.get('stderr', '')[:500]}", file=sys.stderr)

    mix_ok = any(p.name.endswith("instruction_mix.json") for p in out_dir.glob("*.json"))
    if mix_ok:
        print("PASS: Instruction Mix artifact present")
    else:
        print("WARN: Instruction Mix missing", file=sys.stderr)

    return 1 if failures and not mix_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
