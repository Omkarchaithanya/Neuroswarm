#!/usr/bin/env python3
"""Normalize an apx run export directory into code-hotspots.json.

Exit 0 and print ``ok`` when hotspots were written.
Exit 2 and print a short error token when the export is a failed/empty run.
"""
from __future__ import annotations

import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _as_hotspot(item: dict) -> dict | None:
    name = (
        item.get("function")
        or item.get("name")
        or item.get("symbol")
        or item.get("command_line")
        or item.get("path")
    )
    if not name:
        return None
    pct = item.get("pct")
    if pct is None:
        pct = item.get("percent")
    if pct is None:
        pct = item.get("self_pct")
    if pct is None and item.get("samples") is not None:
        pct = item.get("samples")
    try:
        pct_f = float(pct) if pct is not None else 0.0
    except Exception:
        pct_f = 0.0
    out: dict = {"function": str(name)[:200], "pct": pct_f}
    for k in ("pid", "samples"):
        if k in item:
            out[k] = item[k]
    return out


def _fail_token(err: str, run_result: str) -> str:
    low = (err or run_result or "").lower()
    if "neoprof" in low or "deploy-tools" in low or "deploy tools" in low:
        return "neoprof_not_deployed"
    if "license" in low or "login" in low or "auth" in low:
        return "apx_license_or_auth"
    if "agent" in low and "deploy" in low:
        return "AGENT_NOT_DEPLOYED"
    return "apx_recipe_stage_failed"


def _index_tree(node: dict, out: dict[int, int]) -> None:
    try:
        fid = int(node["id"])
        sid = int(node["symbol_id"])
        out[fid] = sid
    except Exception:
        pass
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _index_tree(child, out)


def _hotspots_from_neoprof(json_files: list[Path]) -> list[dict]:
    """Join neoprof callpath_self_samples + call_tree + symbols → ranked hotspots."""
    by_name = {p.name: p for p in json_files}
    self_path = by_name.get("callpath_self_samples.json")
    tree_path = by_name.get("call_tree_samples.json")
    sym_path = by_name.get("symbols.json")
    if not (self_path and tree_path and sym_path):
        # Prefer paths under tool/neoprof even if basename collisions.
        for p in json_files:
            n = p.name
            if n == "callpath_self_samples.json" and self_path is None:
                self_path = p
            elif n == "call_tree_samples.json" and tree_path is None:
                tree_path = p
            elif n == "symbols.json" and "/neoprof/" in str(p).replace("\\", "/") and sym_path is None:
                sym_path = p
            elif n == "symbols.json" and sym_path is None:
                sym_path = p
    if not (self_path and tree_path and sym_path):
        return []

    self_o = _load(self_path)
    tree_o = _load(tree_path)
    sym_raw = _load(sym_path)
    if not isinstance(self_o, dict) or not isinstance(tree_o, dict):
        return []
    symbols = {}
    if isinstance(sym_raw, list):
        for s in sym_raw:
            if isinstance(s, dict) and "id" in s:
                symbols[int(s["id"])] = s
    elif isinstance(sym_raw, dict):
        for s in sym_raw.get("symbols") or []:
            if isinstance(s, dict) and "id" in s:
                symbols[int(s["id"])] = s

    frame_to_sym: dict[int, int] = {}
    _index_tree(tree_o, frame_to_sym)

    counts: dict[str, float] = defaultdict(float)
    for row in self_o.get("rows") or []:
        if not isinstance(row, dict):
            continue
        cd = row.get("column_data") or []
        vals = [float(v) for v in cd if isinstance(v, (int, float))]
        if not vals:
            continue
        samples = vals[0]
        if samples <= 0:
            continue
        try:
            fid = int(row.get("call_frame_id"))
        except Exception:
            continue
        sid = frame_to_sym.get(fid)
        if sid is None:
            continue
        sym = symbols.get(sid) or {}
        name = str(sym.get("name") or f"symbol_{sid}")[:200]
        counts[name] += samples

    total = sum(counts.values()) or 1.0
    hotspots = [
        {"function": name, "pct": round(100.0 * samples / total, 3), "samples": samples}
        for name, samples in counts.items()
    ]
    hotspots.sort(key=lambda h: float(h.get("pct") or 0), reverse=True)
    return hotspots[:25]


def normalize(export_dir: Path, out_json: Path, run_id: str) -> str:
    unpack = export_dir / "_u"
    roots = [export_dir]
    for zpath in sorted(export_dir.rglob("*.zip")):
        try:
            unpack.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zpath, "r") as zf:
                zf.extractall(unpack)
            roots.append(unpack)
        except Exception as e:
            print(f"zip extract warn: {zpath}: {e}", file=sys.stderr)

    json_files: list[Path] = []
    for root in roots:
        json_files.extend(p for p in root.rglob("*.json") if p.is_file())

    meta: dict = {}
    for p in json_files:
        if p.name == "metadata.json":
            raw = _load(p)
            if isinstance(raw, dict):
                meta = raw
                break

    run_result = str(meta.get("run.result") or meta.get("run_result") or "")
    run_error = str(meta.get("run.error") or meta.get("run_error") or "")
    failed = bool(run_error) or ("fail" in run_result.lower())

    hotspots = _hotspots_from_neoprof(json_files)

    if not hotspots:
        # Generic fallback — skip bare symbols.json (no sample weights).
        prefer_names = ("hotspot", "code_hotspot", "functions", "callpath_self", "profile")
        for p in sorted(
            json_files,
            key=lambda x: (0 if any(t in x.name.lower() for t in prefer_names) else 1, -x.stat().st_size),
        ):
            if p.name in {"symbols.json", "metadata.json", "manifest.json", "log.json", "categorization.json"}:
                continue
            raw = _load(p)
            if raw is None:
                continue
            candidates: list = []
            if isinstance(raw, list):
                candidates = raw
            elif isinstance(raw, dict):
                for key in ("hotspots", "functions", "samples", "results", "entries"):
                    v = raw.get(key)
                    if isinstance(v, list) and v:
                        candidates = v
                        break
                if not candidates and isinstance(raw.get("data"), dict):
                    for key in ("hotspots", "functions", "samples"):
                        v = raw["data"].get(key)
                        if isinstance(v, list) and v:
                            candidates = v
                            break
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                hs = _as_hotspot(item)
                if hs and float(hs.get("pct") or 0) > 0:
                    hotspots.append(hs)
            if hotspots:
                break
        hotspots.sort(key=lambda h: float(h.get("pct") or 0), reverse=True)
        hotspots = hotspots[:25]

    if failed:
        err = run_error or run_result or "apx_recipe_stage_failed"
        token = _fail_token(err, run_result)
        Path("work/performix").mkdir(parents=True, exist_ok=True)
        Path("work/performix/last_export_error.txt").write_text(err[:2000], encoding="utf-8")
        print(f"EXPORT_FAIL token={token} result={run_result!r} err={err[:300]!r}", file=sys.stderr)
        return token

    # Instruction Mix exports have static_instruction_mix.csv, not hotspots.
    csv_files = []
    for root in roots:
        csv_files.extend(p for p in root.rglob("static_instruction_mix.csv") if p.is_file())
    if not hotspots and csv_files:
        import csv
        from collections import defaultdict

        rows: list[dict] = []
        with csv_files[0].open(encoding="utf-8", errors="replace") as f:
            rows = list(csv.DictReader(f))
        simd_keys = ("sve", "sve2", "neon", "asimd", "i8mm", "dotprod", "bf16", "simd", "vector")
        simd = total = 0.0
        for row in rows:
            name = " ".join(str(v) for v in row.values()).lower()
            cnt = 0.0
            for c in ("count", "Count", "instructions", "pct", "percent"):
                if c in row:
                    try:
                        cnt = float(row[c])
                        break
                    except Exception:
                        pass
            total += cnt
            if any(s in name for s in simd_keys):
                simd += cnt
        payload = {
            "source": "apx",
            "recipe": "instruction_mix",
            "run_id": run_id,
            "available": 1.0,
            "instruction_mix_rows": rows[:200],
            "summary": {
                "simd_related_count": simd,
                "total_count": total,
                "simd_share_approx": (simd / total) if total else None,
                "rows": len(rows),
                "csv": str(csv_files[0]),
            },
            "metadata": {
                "run.result": run_result,
                "run.recipe_name": meta.get("run.recipe_name"),
                "engine.version": meta.get("engine.version"),
                "target.name": meta.get("target.name"),
            },
        }
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"normalized {out_json} instruction_mix_rows={len(rows)}", file=sys.stderr)
        return "ok"

    if not hotspots:
        print("EXPORT_FAIL token=no_hotspots_in_export", file=sys.stderr)
        return "no_hotspots_in_export"

    payload = {
        "source": "apx",
        "run_id": run_id,
        "hotspots": hotspots,
        "summary": {
            "cycles": meta.get("cycles"),
            "instructions": meta.get("instructions"),
            "ipc": meta.get("ipc"),
        },
        "metadata": {
            "run.result": run_result,
            "run.recipe_name": meta.get("run.recipe_name"),
            "engine.version": meta.get("engine.version"),
            "target.name": meta.get("target.name"),
        },
        "pmu_available": 1.0,
        "recommendations": [
            "Focus hottest function with Arm Performix code_hotspots / cpu_microarchitecture recipes"
        ],
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"normalized {out_json} hotspots={len(hotspots)}", file=sys.stderr)
    return "ok"


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: performix_normalize_export.py EXPORT_DIR OUT_JSON RUN_ID", file=sys.stderr)
        return 1
    token = normalize(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    print(token)
    return 0 if token == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
