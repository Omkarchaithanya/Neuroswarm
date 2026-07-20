#!/usr/bin/env python3
"""Validate KleidiAI activation in llama-server logs or /props."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.kleidiai_verifier import (
    KleidiaiVerifier,
)


def _fetch(url: str, path: str) -> dict | list | str:
    req = urllib.request.Request(url.rstrip("/") + path, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def validate(base_url: str, *, require: bool = False) -> dict:
    verifier = KleidiaiVerifier(require=require)
    props_text = ""
    try:
        props = _fetch(base_url, "/props")
        props_text = json.dumps(props) if not isinstance(props, str) else props
        for line in props_text.splitlines():
            verifier.feed(line + "\n")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "base_url": base_url}
    result = verifier.result()
    return {
        "ok": result.ok,
        "base_url": base_url,
        "kleidiai_detected": result.ok,
        "details": result.__dict__,
        "props_excerpt": props_text[:500],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument("--require", action="store_true")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "work" / "benchmarks" / "kleidiai_validation.json",
    )
    args = parser.parse_args()
    report = validate(args.url, require=args.require)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if args.require and not report.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
