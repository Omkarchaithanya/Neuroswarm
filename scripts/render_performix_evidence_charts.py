#!/usr/bin/env python3
"""Render evidence bar charts from Prometheus query JSON."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "performix" / "screenshots"
DATA = OUT / "queries.json"


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    meta = {
        "01-up": ("01-up-by-job.png", "count by (job, instance) (up)"),
        "02-ipc": ("02-ipc-canonical.png", 'nexus_performix_ipc{job="neuroswarm-gateway"}'),
        "03-hotspots": ("03-hotspots.png", "topk hotspot_pct (canonical job)"),
        "04-age": ("04-snapshot-age.png", "nexus_performix_snapshot_age_seconds"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for key, (fname, title) in meta.items():
        rows = (data.get(key) or {}).get("data", {}).get("result", [])
        labels: list[str] = []
        values: list[float] = []
        for row in rows:
            m = row.get("metric") or {}
            if m.get("function"):
                lab = str(m["function"])
            elif m.get("job"):
                lab = f"{m.get('job')}@{m.get('instance')}"
            else:
                lab = "series"
            labels.append(lab[:48])
            values.append(float(row["value"][1]))
        fig, ax = plt.subplots(figsize=(10, 4.2))
        ax.set_title(title)
        if values:
            ax.barh(range(len(values)), values, color="#264653")
            ax.set_yticks(range(len(values)))
            ax.set_yticklabels(labels)
            ax.invert_yaxis()
            for i, v in enumerate(values):
                ax.text(v, i, f" {v:.4g}", va="center")
        else:
            ax.text(0.5, 0.5, "NO DATA", ha="center", transform=ax.transAxes, color="crimson")
        fig.tight_layout()
        fig.savefig(OUT / fname, dpi=140)
        plt.close(fig)
        print("wrote", fname, values)


if __name__ == "__main__":
    main()
