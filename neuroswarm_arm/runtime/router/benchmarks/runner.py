"""In-package router benchmark runner."""

from __future__ import annotations

from pathlib import Path
import json
import time
from typing import Any

import numpy as np


DEFAULT_CASES = [
    {"query": "Search the web and summarize GitHub issues for the project", "expected": "github"},
    {"query": "Find a page in the browser and capture the visible text", "expected": "browser"},
    {"query": "Store structured data in postgres and query rows", "expected": "postgres"},
    {"query": "Use slack to send a channel update about the release", "expected": "slack"},
    {"query": "Upload an artifact to object storage", "expected": "s3"},
    {"query": "Look up a related web source before answering", "expected": "web-search"},
]


def _family(tool_id: str) -> str:
    tid = str(tool_id or "").lower().strip()
    if "." in tid:
        return tid.split(".", 1)[0]
    # Coarse aliases
    if tid in {"web-search", "web"}:
        return "web"
    return tid


def _expected_families(expected: str) -> set[str]:
    exp = str(expected or "").lower().strip()
    if exp in {"web-search", "web"}:
        return {"web", "web-search"}
    return {exp, _family(exp)}


def _matches_expected(expected: str, tool_id: str, tool_name: str = "") -> bool:
    """Family-aware match: expected=github hits github.create_issue."""
    exp = str(expected or "").lower().strip()
    tid = str(tool_id or "").lower().strip()
    name = str(tool_name or "").lower().strip()
    if not exp:
        return False
    if exp in {tid, name}:
        return True
    families = _expected_families(exp)
    if _family(tid) in families:
        return True
    if tid.startswith(exp + ".") or exp.startswith(tid + "."):
        return True
    # Name contains family token (e.g. "GitHub Create Issue")
    for fam in families:
        if fam and fam in name.replace(" ", "-"):
            return True
    return False


def run_router_benchmark(router: Any, cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    suite = cases or DEFAULT_CASES
    latencies: list[float] = []
    top1 = top3 = top5 = 0
    fp = fn = 0
    per_case = []
    token_reductions: list[float] = []

    for case in suite:
        query = str(case["query"])
        expected = str(case.get("expected", ""))
        t0 = time.perf_counter()
        result = router.route(query, top_k=max(5, router.config.top_k))
        ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(ms)
        ids = list(result.tool_ids)
        names = list(result.tool_names)
        hit3 = any(
            _matches_expected(expected, tid, names[i] if i < len(names) else "")
            for i, tid in enumerate(ids[:3])
        )
        hit5 = any(
            _matches_expected(expected, tid, names[i] if i < len(names) else "")
            for i, tid in enumerate(ids[:5])
        )
        hit1 = bool(ids) and _matches_expected(
            expected, ids[0], names[0] if names else ""
        )
        if hit1:
            top1 += 1
        if hit3:
            top3 += 1
        if hit5:
            top5 += 1
        else:
            fn += 1
            fp += 1
        token_reductions.append(result.token_reduction_ratio())
        per_case.append(
            {
                "query": query,
                "expected": expected,
                "picked": ids,
                "confidence": result.confidence_top1,
                "latency_ms": round(ms, 3),
                "hit1": hit1,
                "hit3": hit3,
            }
        )

    total = max(1, len(suite))
    arr = np.asarray(latencies, dtype=np.float64) if latencies else np.asarray([0.0])

    # Embedding / ANN throughput probes
    probe_text = "benchmark probe tool routing throughput"
    emb_times = []
    for _ in range(20):
        t0 = time.perf_counter()
        router.embedder.encode(probe_text)
        emb_times.append((time.perf_counter() - t0) * 1000.0)
    ann_times = []
    q = router.embedder.encode(probe_text)
    for _ in range(50):
        t0 = time.perf_counter()
        router.index.search(q, 3)
        ann_times.append((time.perf_counter() - t0) * 1000.0)

    mem_mb = 0.0
    try:
        import psutil

        mem_mb = psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        pass

    out = {
        "status": "ok",
        "top1_accuracy": round(top1 / total, 4),
        "top3_accuracy": round(top3 / total, 4),
        "top5_accuracy": round(top5 / total, 4),
        "false_positives": fp,
        "false_negatives": fn,
        "latency_ms": {
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "mean": float(arr.mean()),
        },
        "embedding_throughput_qps": round(1000.0 / max(1e-6, float(np.mean(emb_times))), 2),
        "ann_throughput_qps": round(1000.0 / max(1e-6, float(np.mean(ann_times))), 2),
        "avg_token_reduction": round(float(np.mean(token_reductions)) if token_reductions else 0.0, 4),
        "memory_mb": round(mem_mb, 2),
        "ann_backend": getattr(router.index, "backend_name", "unknown"),
        "embedding_backend": router.embedder.backend_name,
        "tools_indexed": router.registry.size(),
        "cases": per_case,
    }
    return out


def write_benchmark(result: dict[str, Any], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return path
