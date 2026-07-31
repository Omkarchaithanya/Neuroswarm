#!/usr/bin/env python3
"""Render a flame-style PNG from published apx code_hotspots JSON.

Does not invent metrics — refuses missing/empty/demo sources.
Usage:
  python scripts/render_performix_flame.py \\
    --input docs/evidence/performix/01-code_hotspots.json \\
    --output docs/evidence/performix/screenshots/05-code-hotspots-flame.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"expected object in {path}")
    src = str(data.get("source") or "")
    if src in {"demo", "synthetic", "unavailable", ""}:
        raise SystemExit(f"refusing source={src!r} — need source=apx")
    hotspots = data.get("hotspots") or []
    if not hotspots:
        raise SystemExit("no hotspots — refusing empty chart")
    return data


def _short(name: str, n: int = 42) -> str:
    s = str(name).replace("<", "").replace(">", "")
    return s if len(s) <= n else s[: n - 1] + "…"


def render(data: dict, out: Path, *, top_n: int = 12) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    rows = sorted(
        (h for h in data["hotspots"] if isinstance(h, dict)),
        key=lambda h: float(h.get("pct") or 0.0),
        reverse=True,
    )[:top_n]
    total = sum(float(h.get("pct") or 0.0) for h in rows) or 1.0
    run_id = data.get("run_id") or data.get("recipe") or "apx"
    src = data.get("source", "apx")

    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=140)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 3.2)
    ax.axis("off")
    ax.set_title(
        f"Arm Performix code_hotspots (source={src}, run={run_id})\n"
        "Flame-style view generated from published apx JSON — not demo fill",
        fontsize=11,
        pad=12,
    )

    # Stacked root row (self-% normalized to 100 for visual width)
    x = 0.0
    cmap = plt.get_cmap("YlOrRd")
    for i, h in enumerate(rows):
        pct = float(h.get("pct") or 0.0)
        w = 100.0 * pct / total
        color = cmap(0.35 + 0.55 * (pct / max(float(rows[0].get("pct") or 1.0), 1e-6)))
        rect = FancyBboxPatch(
            (x, 1.35),
            w,
            1.1,
            boxstyle="round,pad=0.01,rounding_size=0.5",
            linewidth=0.4,
            edgecolor="#333333",
            facecolor=color,
        )
        ax.add_patch(rect)
        if w >= 6.5:
            ax.text(
                x + w / 2,
                1.9,
                f"{_short(h.get('function', '?'), 28)}\n{pct:.1f}%",
                ha="center",
                va="center",
                fontsize=7,
                color="#1a1a1a",
            )
        x += w

    # Ranked list (left) for frames too thin to label on the flame
    y = 1.0
    ax.text(0, y, "Top frames (self %)", fontsize=9, fontweight="bold")
    y -= 0.18
    for h in rows[:8]:
        pct = float(h.get("pct") or 0.0)
        ax.text(0, y, f"{pct:6.2f}%  {_short(h.get('function', '?'), 70)}", fontsize=7, family="monospace")
        y -= 0.14

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--top-n", type=int, default=12)
    args = p.parse_args()
    data = _load(args.input)
    render(data, args.output, top_n=args.top_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
