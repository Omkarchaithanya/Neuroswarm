#!/usr/bin/env python3
"""Validate KleidiAI activation via throughput benchmark (not log regex).

Primary gate compares median ``timings.predicted_per_second`` against
``benchmarks/kleidiai_baselines.json``. Pass threshold is a conservative 15%
floor over ``no_kleidiai_tok_s`` — validated against 26-64% real observed Axion
gains (Qwen +64%, Llama-3.2-3B +26%, DeepSeek-R1-8B +34%, 2026-07-22). Log scrape is informational only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neuroswarm_arm.runtime.dipa.backends.llama_cpp.kleidiai_verifier import (
    KleidiaiVerifier,
    KleidiaiVerifyResult,
)

BASELINES_PATH = ROOT / "benchmarks" / "kleidiai_baselines.json"
# 15% floor — conservative vs 26-64% observed Axion KleidiAI gains (2026-07-22).
THRESHOLD_PCT = 15
BENCHMARK_PROMPT: dict[str, Any] = {
    "model": "any",
    "messages": [{"role": "user", "content": "What is 2+2? Answer briefly."}],
    "max_tokens": 100,
}
KLEIDIAI_WARNING_RE = re.compile(r"kleidiai.*(?:warning|no kernel)", re.IGNORECASE)


def _fetch(url: str, path: str, *, method: str = "GET", payload: dict | None = None) -> Any:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=body,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def load_baselines(path: Path | None = None) -> dict[str, dict[str, Any]]:
    src = path or BASELINES_PATH
    if not src.exists():
        return {}
    data = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def baseline_reference_gain_pct(entry: dict[str, Any]) -> float | None:
    """Return catalogued gain_pct or derive from no_kleidiai/kleidiai reference speeds."""
    catalogued = entry.get("gain_pct")
    if catalogued is not None:
        try:
            return float(catalogued)
        except (TypeError, ValueError):
            pass
    no_k = entry.get("no_kleidiai_tok_s")
    ki_k = entry.get("kleidiai_tok_s")
    if no_k is None or ki_k is None:
        return None
    try:
        return ((float(ki_k) - float(no_k)) / float(no_k)) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _walk_strings(obj: Any, out: list[str]) -> None:
    if isinstance(obj, dict):
        for value in obj.values():
            _walk_strings(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_strings(item, out)
    elif isinstance(obj, str):
        out.append(obj)


def extract_model_basename(props_or_models: Any) -> str | None:
    """Extract GGUF filename basename from /props or /v1/models payload."""
    strings: list[str] = []
    _walk_strings(props_or_models, strings)
    for text in strings:
        lowered = text.replace("\\", "/").lower()
        if ".gguf" in lowered:
            return Path(lowered).name
    if isinstance(props_or_models, dict):
        models = props_or_models.get("data")
        if isinstance(models, list) and models:
            first = models[0]
            if isinstance(first, dict):
                for key in ("id", "model", "name"):
                    val = first.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip().lower()
    return None


def resolve_model(base_url: str) -> str | None:
    for path in ("/props", "/v1/models"):
        try:
            data = _fetch(base_url, path)
            model = extract_model_basename(data)
            if model:
                return model
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            continue
    return None


def _parse_predicted_tok_s(response: dict[str, Any]) -> float | None:
    timings = response.get("timings")
    if not isinstance(timings, dict):
        return None
    value = timings.get("predicted_per_second")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sample_predicted_tok_s(base_url: str, *, sleep_fn=time.sleep) -> float | None:
    """One benchmark sample; retry once after 5s on transient errors."""
    for attempt in range(2):
        try:
            data = _fetch(
                base_url,
                "/v1/chat/completions",
                method="POST",
                payload=BENCHMARK_PROMPT,
            )
            if isinstance(data, dict):
                tok_s = _parse_predicted_tok_s(data)
                if tok_s is not None:
                    return tok_s
        except urllib.error.HTTPError as exc:
            if exc.code == 503 and attempt == 0:
                sleep_fn(5)
                continue
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 0:
                sleep_fn(5)
                continue
            return None
        break
    return None


def run_benchmark_samples(
    base_url: str,
    *,
    sleep_fn=time.sleep,
    sample_fn=None,
) -> list[float]:
    sampler = sample_fn or (lambda url: sample_predicted_tok_s(url, sleep_fn=sleep_fn))
    samples: list[float] = []
    for _ in range(3):
        value = sampler(base_url)
        if value is not None:
            samples.append(value)
    return samples


def median_tok_s(samples: list[float]) -> float | None:
    if not samples:
        return None
    return float(statistics.median(samples))


def _fetch_log_text(base_url: str, log_text: str = "") -> str:
    if log_text:
        return log_text
    chunks: list[str] = []
    for path in ("/props", "/health", "/v1/models"):
        try:
            data = _fetch(base_url, path)
            if isinstance(data, (dict, list)):
                chunks.append(json.dumps(data, indent=2))
            elif isinstance(data, str):
                chunks.append(data)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            continue
    return "\n".join(chunks)


def scrape_log_info(log_text: str) -> dict[str, Any]:
    warning_lines: list[str] = []
    for line in log_text.splitlines():
        if KLEIDIAI_WARNING_RE.search(line):
            warning_lines.append(line.strip())
    return {
        "kleidiai_warnings_present": bool(warning_lines),
        "warning_lines": warning_lines,
    }


def serialize_verify_result(result: KleidiaiVerifyResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["cpu_features"] = asdict(result.cpu_features)
    return payload


def build_log_scrape_info(base_url: str, log_text: str = "") -> dict[str, Any]:
    text = _fetch_log_text(base_url, log_text)
    info = scrape_log_info(text)
    verifier = KleidiaiVerifier(require=False)
    verifier.feed_many(text)
    info["verifier"] = serialize_verify_result(verifier.result())
    return info


def validate(
    base_url: str,
    *,
    require: bool = False,
    log_text: str = "",
    baselines: dict[str, dict[str, Any]] | None = None,
    sleep_fn=time.sleep,
    sample_fn=None,
) -> dict[str, Any]:
    """Benchmark-based KleidiAI validation. Log scrape is informational only."""
    table = baselines if baselines is not None else load_baselines()
    model = resolve_model(base_url)
    samples = run_benchmark_samples(base_url, sleep_fn=sleep_fn, sample_fn=sample_fn)
    median = median_tok_s(samples)

    if len(samples) < 2:
        return {
            "ok": False,
            "base_url": base_url,
            "model": model,
            "benchmark": {
                "samples_tok_s": samples,
                "median_tok_s": median,
                "baseline_tok_s": None,
                "gain_pct": None,
                "threshold_pct": THRESHOLD_PCT,
            },
            "log_scrape_info": build_log_scrape_info(base_url, log_text),
            "message": (
                f"insufficient benchmark samples ({len(samples)}/3 succeeded); "
                "server unreachable or still loading"
            ),
            "hard_fail": True,
        }

    baseline_entry = table.get(model or "", {}) if model else {}
    baseline_tok_s = baseline_entry.get("no_kleidiai_tok_s")
    reference_gain_pct = baseline_reference_gain_pct(baseline_entry)
    gain_pct: float | None = None
    if baseline_tok_s is not None and median is not None:
        gain_pct = ((median - float(baseline_tok_s)) / float(baseline_tok_s)) * 100.0

    benchmark = {
        "samples_tok_s": samples,
        "median_tok_s": median,
        "baseline_tok_s": baseline_tok_s,
        "reference_gain_pct": reference_gain_pct,
        "gain_pct": gain_pct,
        "threshold_pct": THRESHOLD_PCT,
    }
    log_scrape_info = build_log_scrape_info(base_url, log_text)

    if not model or baseline_tok_s is None:
        observed = f"{median:.2f}" if median is not None else "n/a"
        return {
            "ok": True,
            "base_url": base_url,
            "model": model,
            "benchmark": benchmark,
            "log_scrape_info": log_scrape_info,
            "message": (
                f"no baseline for this model — recorded observation only "
                f"(median={observed} tok/s)"
            ),
            "hard_fail": False,
        }

    threshold = float(baseline_tok_s) * (1.0 + THRESHOLD_PCT / 100.0)
    passed = median is not None and median >= threshold
    if passed:
        message = (
            f"KleidiAI benchmark pass: median {median:.2f} tok/s >= "
            f"baseline {baseline_tok_s} * 1.{THRESHOLD_PCT} ({threshold:.2f})"
        )
        return {
            "ok": True,
            "base_url": base_url,
            "model": model,
            "benchmark": benchmark,
            "log_scrape_info": log_scrape_info,
            "message": message,
            "hard_fail": False,
        }

    message = (
        f"KleidiAI benchmark regression: median {median:.2f} tok/s < "
        f"threshold {threshold:.2f} (baseline {baseline_tok_s})"
    )
    return {
        "ok": False,
        "base_url": base_url,
        "model": model,
        "benchmark": benchmark,
        "log_scrape_info": log_scrape_info,
        "message": message,
        "hard_fail": False,
        "warn_only": not require,
    }


def should_exit_nonzero(report: dict[str, Any], *, require: bool) -> bool:
    if report.get("hard_fail"):
        return True
    if require and not report.get("ok"):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=os.getenv("NSA_TIER2_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument("--require", action="store_true")
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional llama-server log file for informational scrape only",
    )
    parser.add_argument(
        "--baselines",
        type=Path,
        default=BASELINES_PATH,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "work" / "benchmarks" / "kleidiai_validation.json",
    )
    args = parser.parse_args()

    log_text = ""
    if args.log_file and args.log_file.exists():
        log_text = args.log_file.read_text(encoding="utf-8", errors="ignore")

    report = validate(
        args.url,
        require=args.require,
        log_text=log_text,
        baselines=load_baselines(args.baselines),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if should_exit_nonzero(report, require=args.require):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
