"""AROP Axion preflight checks — callable from CLI or scripts/arop-preflight.sh."""

from __future__ import annotations

import argparse
import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neuroswarm_arm.arop.exceptions import AropMetricInvalid, AropMetricMissing
from neuroswarm_arm.arop.metrics_parser import load_json, parse_code_hotspots

LOG = logging.getLogger(__name__)

# Idle / load-time captures often have tiny sample counts (e.g. 12).
MIN_TOTAL_SAMPLES = 100


@dataclass(slots=True)
class PreflightResult:
    ok: bool
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def log(self) -> None:
        for line in self.checks:
            LOG.info("%s", line)
        for line in self.warnings:
            LOG.warning("%s", line)
        for line in self.errors:
            LOG.error("%s", line)


def _cpu_features_report() -> list[str]:
    """Honest host feature report — never invent SME2/MTE/CSS V3."""
    lines: list[str] = [
        f"host platform={platform.platform()}",
        f"host machine={platform.machine()}",
        f"host python={platform.python_version()}",
    ]
    # Linux /proc/cpuinfo flags when present
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        text = cpuinfo.read_text(encoding="utf-8", errors="replace")
        flags: set[str] = set()
        for line in text.splitlines():
            if line.lower().startswith("features") or line.lower().startswith("flags"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    flags.update(parts[1].split())
        interesting = sorted(
            f
            for f in flags
            if f.lower()
            in {
                "asimd",
                "neon",
                "sve",
                "sve2",
                "sme",
                "sme2",
                "i8mm",
                "bf16",
                "atomics",
            }
        )
        if interesting:
            lines.append(f"cpuinfo features (subset)={','.join(interesting)}")
        else:
            lines.append("cpuinfo: no NEON/SVE/SME flags parsed (or absent)")
        # Explicit honesty: do not claim MTE/CSS V3 from absence of evidence
        lines.append(
            "honesty: AROP v1 does not claim CSS V3, MTE, or SME2 acceleration "
            "unless separately measured"
        )
    else:
        lines.append(
            "cpuinfo unavailable (non-Linux host) — skip Arm feature parse; "
            "do not invent KleidiAI/SME2 status"
        )
    return lines


def _kleidi_log_hint() -> str:
    """Best-effort KleidiAI mention in tier1 logs — informational only."""
    if shutil.which("docker") is None:
        return "KleidiAI: docker not on PATH — skip log probe"
    try:
        ps = subprocess.run(
            ["docker", "compose", "ps"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if ps.returncode != 0 or "tier1" not in (ps.stdout or ""):
            return "KleidiAI: tier1 service not running via docker compose — skip"
        logs = subprocess.run(
            ["docker", "compose", "logs", "--tail", "200", "tier1"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        blob = (logs.stdout or "") + (logs.stderr or "")
        if "kleidi" in blob.lower():
            return "KleidiAI: string found in recent tier1 logs (informational)"
        return "KleidiAI: no string in recent tier1 logs (informational — not a FAIL)"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"KleidiAI: log probe failed ({exc}) — informational"


def _total_samples(payload: dict[str, Any]) -> float | None:
    hotspots = payload.get("hotspots")
    if not isinstance(hotspots, list) or not hotspots:
        return None
    total = 0.0
    saw = False
    for row in hotspots:
        if not isinstance(row, dict) or "samples" not in row:
            continue
        val = row["samples"]
        if val is None:
            continue
        try:
            total += float(val)
            saw = True
        except (TypeError, ValueError):
            continue
    return total if saw else None


def run_preflight(hotspots_path: Path) -> PreflightResult:
    """Run honesty gates before live --apply."""
    result = PreflightResult(ok=True)

    allow = os.getenv("NSA_PERFORMIX_ALLOW_DEMO", "0")
    if allow not in {"0", "false", "False", "no", "NO", ""}:
        result.ok = False
        result.errors.append(
            f"FAIL: NSA_PERFORMIX_ALLOW_DEMO={allow!r} — must be 0 for live AROP"
        )
    else:
        result.checks.append("OK: NSA_PERFORMIX_ALLOW_DEMO=0")

    for line in _cpu_features_report():
        result.checks.append(f"CPU: {line}")

    result.checks.append(_kleidi_log_hint())

    if not hotspots_path.is_file():
        result.ok = False
        result.errors.append(f"FAIL: hotspots file missing: {hotspots_path}")
        return result

    try:
        payload = load_json(hotspots_path)
        metrics = parse_code_hotspots(payload)
    except (AropMetricMissing, AropMetricInvalid) as exc:
        result.ok = False
        result.errors.append(f"FAIL: {exc}")
        return result

    result.checks.append(
        f"OK: source={metrics.source!r} top={metrics.top_function!r} pct={metrics.top_pct}"
    )

    if metrics.contaminated:
        result.ok = False
        reason = metrics.contamination_reason or "contaminated profile"
        result.errors.append(f"FAIL: contaminated — {reason}")
        return result
    result.checks.append("OK: not contaminated (Proposal A)")

    samples = _total_samples(payload)
    if samples is None:
        result.warnings.append(
            "WARN: hotspots lack 'samples' field — cannot verify low-sample gate"
        )
    elif samples < MIN_TOTAL_SAMPLES:
        result.ok = False
        result.errors.append(
            f"FAIL: low-sample profile (total samples={samples:.0f} < {MIN_TOTAL_SAMPLES}) "
            "— likely idle/load-time capture; re-profile under chat load"
        )
    else:
        result.checks.append(f"OK: sample count={samples:.0f} (>= {MIN_TOTAL_SAMPLES})")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AROP Axion preflight honesty gates")
    parser.add_argument(
        "hotspots",
        nargs="?",
        default="work/arop/performix/code-hotspots.json",
        type=Path,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    print("=== AROP preflight ===")
    result = run_preflight(args.hotspots)
    for line in result.checks:
        print(line)
    for line in result.warnings:
        print(line)
    for line in result.errors:
        print(line, flush=True)
    if result.ok:
        print("=== preflight PASS ===")
        print(
            f"Next: dry-run, then python -m neuroswarm_arm.arop.evolve_cycle --apply "
            f"--hotspots {args.hotspots} ..."
        )
        return 0
    print("=== preflight FAIL ===", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
