#!/usr/bin/env python3
"""Detect ARM CPU features for KleidiAI / llama.cpp CMake generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as script from repo root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from neuroswarm_arm.runtime.dipa.control.hardware_detector import (  # noqa: E402
    ControlHardwareDetector,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect CPU features for NEXUS-ARM")
    parser.add_argument("-o", "--output", type=Path, help="Write JSON profile")
    args = parser.parse_args(argv)
    profile = ControlHardwareDetector().detect().to_dict()
    text = json.dumps(profile, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
