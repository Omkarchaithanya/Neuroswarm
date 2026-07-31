"""Fail-loud metrics parsers for AROP v1.

HARD RULE: never default missing/null fields to 0. Raise AropMetricMissing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.error import URLError
from urllib.request import urlopen

from neuroswarm_arm.arop.exceptions import AropMetricInvalid, AropMetricMissing

LOG = logging.getLogger(__name__)

_UNKNOWN_SYMBOL_RE = re.compile(r"Unknown symbol\s*@\s*0x", re.IGNORECASE)
_LOAD_TIME_SYSCALLS = frozenset(
    {
        "posix_fallocate",
        "fallocate",
        "mmap",
        "__mmap",
        "read",
    }
)
_REJECTED_SOURCES = frozenset({"demo", "synthetic", "unavailable", ""})

# Prometheus metric required for decode tok/s (llama-server --metrics).
THROUGHPUT_METRIC = "llamacpp:predicted_tokens_seconds"


def require(payload: Mapping[str, Any], path: str, source: str) -> Any:
    """Return the value at dotted ``path`` or raise. Never substitutes a default."""
    cur: Any = payload
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            raise AropMetricMissing(f"{source}: missing required field {path!r}")
        cur = cur[part]
    if cur is None:
        raise AropMetricMissing(f"{source}: field {path!r} is null")
    return cur


def _require_apx_source(payload: Mapping[str, Any], source: str) -> None:
    if "source" not in payload:
        raise AropMetricMissing(f"{source}: missing required field 'source'")
    src = payload["source"]
    if src is None:
        raise AropMetricMissing(f"{source}: field 'source' is null")
    src_s = str(src).strip().lower()
    if src_s in _REJECTED_SOURCES or src_s != "apx":
        raise AropMetricInvalid(
            f"{source}: dishonest or non-apx source={src!r} (require source=apx)"
        )


def _parse_prometheus(text: str) -> dict[str, float]:
    """Parse Prometheus text exposition (same pattern as kv_cache_status)."""
    out: dict[str, float] = {}
    if not text:
        return out
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        try:
            out[name] = float(parts[-1])
        except ValueError:
            continue
    return out


@dataclass(frozen=True, slots=True)
class HotspotFrame:
    function: str
    pct: float


@dataclass(frozen=True, slots=True)
class HotspotMetrics:
    source: str
    hotspots: tuple[HotspotFrame, ...]
    top_function: str
    top_pct: float
    unknown_symbol_pct: float
    contaminated: bool
    contamination_reason: str | None


@dataclass(frozen=True, slots=True)
class SimdMetrics:
    source: str
    neon_pct: float
    sve_pct: float
    simd_instruction_pct: float


@dataclass(frozen=True, slots=True)
class CascadeMetrics:
    overall_acceptance_rate: float
    sample_size: int
    avg_latency_ms: float
    tier1_hit_rate: float
    tier2_hit_rate: float
    tier3_hit_rate: float


@dataclass(frozen=True, slots=True)
class GovernorMetrics:
    thinking_tokens_avg: float
    cap_b_used: int
    sample_size: int


@dataclass(frozen=True, slots=True)
class ThroughputMetrics:
    predicted_tokens_seconds: float
    base_url: str


@dataclass(frozen=True, slots=True)
class MetricsBundle:
    hotspots: HotspotMetrics | None = None
    simd: SimdMetrics | None = None
    cascade: CascadeMetrics | None = None
    governor: GovernorMetrics | None = None
    throughput: ThroughputMetrics | None = None
    errors: dict[str, str] = field(default_factory=dict)


def parse_code_hotspots(payload: Mapping[str, Any]) -> HotspotMetrics:
    """Parse apx code_hotspots JSON. Does NOT read summary.ipc (null in real output)."""
    src_name = "code_hotspots"
    _require_apx_source(payload, src_name)
    raw_hotspots = require(payload, "hotspots", src_name)
    if not isinstance(raw_hotspots, list) or not raw_hotspots:
        raise AropMetricMissing(f"{src_name}: hotspots must be a non-empty list")

    frames: list[HotspotFrame] = []
    for i, row in enumerate(raw_hotspots):
        if not isinstance(row, Mapping):
            raise AropMetricInvalid(f"{src_name}: hotspots[{i}] must be an object")
        fn = require(row, "function", f"{src_name}.hotspots[{i}]")
        pct = require(row, "pct", f"{src_name}.hotspots[{i}]")
        if not isinstance(fn, str) or not fn.strip():
            raise AropMetricInvalid(f"{src_name}: hotspots[{i}].function must be non-empty str")
        try:
            pct_f = float(pct)
        except (TypeError, ValueError) as exc:
            raise AropMetricInvalid(
                f"{src_name}: hotspots[{i}].pct must be numeric, got {pct!r}"
            ) from exc
        frames.append(HotspotFrame(function=fn.strip(), pct=pct_f))

    top = frames[0]
    unknown_pct = sum(f.pct for f in frames if _UNKNOWN_SYMBOL_RE.search(f.function))
    top_base = top.function.split("(")[0].strip().lstrip("<").split()[0] if top.function else ""
    # Match whole-token load-time syscalls (not substrings of lib names).
    contaminated = False
    reason: str | None = None
    if unknown_pct > 20.0:
        contaminated = True
        reason = f"Unknown symbol @ 0x share {unknown_pct:.2f}% > 20%"
    else:
        top_lower = top.function.lower()
        for syscall in _LOAD_TIME_SYSCALLS:
            # Exact token match on function name (strip angle brackets / path noise).
            tokens = re.split(r"[^a-zA-Z0-9_]+", top_lower)
            if syscall.lower() in tokens:
                contaminated = True
                reason = f"top hotspot is load-time syscall {syscall!r}: {top.function!r}"
                break

    return HotspotMetrics(
        source=str(require(payload, "source", src_name)),
        hotspots=tuple(frames),
        top_function=top.function,
        top_pct=top.pct,
        unknown_symbol_pct=unknown_pct,
        contaminated=contaminated,
        contamination_reason=reason,
    )


def parse_instruction_mix(payload: Mapping[str, Any]) -> SimdMetrics:
    """Parse apx instruction_mix JSON. Exposes instruction shares, not utilization."""
    src_name = "instruction_mix"
    _require_apx_source(payload, src_name)
    neon = require(payload, "summary.neon_pct", src_name)
    sve = require(payload, "summary.sve_pct", src_name)
    try:
        neon_f = float(neon)
        sve_f = float(sve)
    except (TypeError, ValueError) as exc:
        raise AropMetricInvalid(
            f"{src_name}: neon_pct/sve_pct must be numeric, got {neon!r}/{sve!r}"
        ) from exc
    return SimdMetrics(
        source=str(require(payload, "source", src_name)),
        neon_pct=neon_f,
        sve_pct=sve_f,
        simd_instruction_pct=neon_f + sve_f,
    )


def parse_cascade_acceptance(payload: Mapping[str, Any]) -> CascadeMetrics:
    """Parse benchmarks/cascade_acceptance_live.py JSON output."""
    src_name = "cascade_acceptance"
    rate = require(payload, "overall_acceptance_rate", src_name)
    sample = require(payload, "sample_size", src_name)
    latency = require(payload, "avg_latency_ms", src_name)
    per_request = require(payload, "per_request", src_name)
    if not isinstance(per_request, list) or not per_request:
        raise AropMetricMissing(f"{src_name}: per_request must be a non-empty list")

    tiers: list[int] = []
    for i, row in enumerate(per_request):
        if not isinstance(row, Mapping):
            raise AropMetricInvalid(f"{src_name}: per_request[{i}] must be an object")
        tier = require(row, "tier_used", f"{src_name}.per_request[{i}]")
        try:
            tiers.append(int(tier))
        except (TypeError, ValueError) as exc:
            raise AropMetricInvalid(
                f"{src_name}: per_request[{i}].tier_used must be int, got {tier!r}"
            ) from exc

    n = len(tiers)
    t1 = sum(1 for t in tiers if t == 1) / n
    t2 = sum(1 for t in tiers if t == 2) / n
    t3 = sum(1 for t in tiers if t == 3) / n
    try:
        rate_f = float(rate)
        latency_f = float(latency)
        sample_i = int(sample)
    except (TypeError, ValueError) as exc:
        raise AropMetricInvalid(
            f"{src_name}: overall_acceptance_rate/sample_size/avg_latency_ms must be numeric"
        ) from exc
    return CascadeMetrics(
        overall_acceptance_rate=rate_f,
        sample_size=sample_i,
        avg_latency_ms=latency_f,
        tier1_hit_rate=t1,
        tier2_hit_rate=t2,
        tier3_hit_rate=t3,
    )


def parse_governor(payload: Mapping[str, Any]) -> GovernorMetrics:
    """Parse benchmarks/governor_live.py JSON; map avg_tokens_run_b → thinking_tokens_avg."""
    src_name = "governor"
    avg_b = require(payload, "avg_tokens_run_b", src_name)
    cap_b = require(payload, "cap_b_used", src_name)
    sample = require(payload, "sample_size", src_name)
    try:
        return GovernorMetrics(
            thinking_tokens_avg=float(avg_b),
            cap_b_used=int(cap_b),
            sample_size=int(sample),
        )
    except (TypeError, ValueError) as exc:
        raise AropMetricInvalid(
            f"{src_name}: avg_tokens_run_b/cap_b_used/sample_size must be numeric"
        ) from exc


def read_tier_throughput(base_url: str, *, metrics_text: str | None = None) -> ThroughputMetrics:
    """Read llamacpp:predicted_tokens_seconds from llama-server /metrics.

    If ``metrics_text`` is provided (tests/offline), skip the HTTP fetch.
    """
    src_name = "llama_metrics"
    url = base_url.rstrip("/")
    text = metrics_text
    if text is None:
        metrics_url = f"{url}/metrics"
        try:
            with urlopen(metrics_url, timeout=10) as resp:  # noqa: S310 — operator URL
                text = resp.read().decode("utf-8", errors="replace")
        except (URLError, OSError, TimeoutError) as exc:
            raise AropMetricInvalid(f"{src_name}: failed to fetch {metrics_url}: {exc}") from exc

    if text is None:
        raise AropMetricMissing(f"{src_name}: empty metrics body")

    parsed = _parse_prometheus(text)
    if THROUGHPUT_METRIC not in parsed:
        raise AropMetricMissing(
            f"{src_name}: missing required metric {THROUGHPUT_METRIC!r} in /metrics"
        )
    return ThroughputMetrics(
        predicted_tokens_seconds=float(parsed[THROUGHPUT_METRIC]),
        base_url=url,
    )


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AropMetricMissing(f"file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AropMetricInvalid(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AropMetricInvalid(f"JSON root must be object at {path}")
    return data


def collect_bundle(
    *,
    hotspots_path: Path | None = None,
    instruction_mix_path: Path | None = None,
    acceptance_path: Path | None = None,
    governor_path: Path | None = None,
    tier_metrics_url: str | None = None,
    tier_metrics_text: str | None = None,
) -> MetricsBundle:
    """Assemble MetricsBundle; per-source failures become None + errors entry.

    Never substitutes numeric defaults. Rules must skip when a required slot is None.
    """
    errors: dict[str, str] = {}
    hotspots: HotspotMetrics | None = None
    simd: SimdMetrics | None = None
    cascade: CascadeMetrics | None = None
    governor: GovernorMetrics | None = None
    throughput: ThroughputMetrics | None = None

    if hotspots_path is not None:
        try:
            hotspots = parse_code_hotspots(load_json(hotspots_path))
        except (AropMetricMissing, AropMetricInvalid) as exc:
            errors["hotspots"] = str(exc)
            LOG.warning("hotspots unavailable: %s", exc)

    if instruction_mix_path is not None:
        try:
            simd = parse_instruction_mix(load_json(instruction_mix_path))
        except (AropMetricMissing, AropMetricInvalid) as exc:
            errors["simd"] = str(exc)
            LOG.warning("instruction_mix unavailable: %s", exc)

    if acceptance_path is not None:
        try:
            cascade = parse_cascade_acceptance(load_json(acceptance_path))
        except (AropMetricMissing, AropMetricInvalid) as exc:
            errors["cascade"] = str(exc)
            LOG.warning("cascade acceptance unavailable: %s", exc)

    if governor_path is not None:
        try:
            governor = parse_governor(load_json(governor_path))
        except (AropMetricMissing, AropMetricInvalid) as exc:
            errors["governor"] = str(exc)
            LOG.warning("governor unavailable: %s", exc)

    if tier_metrics_url is not None or tier_metrics_text is not None:
        try:
            throughput = read_tier_throughput(
                tier_metrics_url or "http://localhost:8081",
                metrics_text=tier_metrics_text,
            )
        except (AropMetricMissing, AropMetricInvalid) as exc:
            errors["throughput"] = str(exc)
            LOG.warning("throughput unavailable: %s", exc)

    return MetricsBundle(
        hotspots=hotspots,
        simd=simd,
        cascade=cascade,
        governor=governor,
        throughput=throughput,
        errors=errors,
    )
