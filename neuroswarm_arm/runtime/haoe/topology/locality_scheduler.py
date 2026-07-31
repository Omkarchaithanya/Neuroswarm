"""Dual-mode locality scheduler — NUMA when multi-node, cache-aware cores on Axion.

GCP C4A (Axion) exposes a single UMA domain. Cross-NUMA draft@0 / verify@1 is
impossible there. This module preserves *locality* via:

- multi_numa: numactl node bind (existing numa_status.bind_planned)
- single_uma / cache_aware: disjoint CPU sets for draft vs verifier tiers

Default Axion 8-core partition (matches TIER1/2/3 thread counts 2/3/3):
  tier1 (draft):    cores 0-1
  tier2 (verifier): cores 2-4
  tier3 (verifier): cores 5-7
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


def locality_mode_env() -> str:
    """NSA_LOCALITY_MODE: auto | numa | uma_affinity | off (default auto)."""
    raw = (os.getenv("NSA_LOCALITY_MODE") or "auto").strip().lower()
    if raw in {"auto", "numa", "uma_affinity", "off", "cache_aware"}:
        if raw == "cache_aware":
            return "uma_affinity"
        return raw
    return "auto"


def _parse_core_list(text: str) -> list[int]:
    """Parse '0-1' or '0,1,2' or '2-4,6' into sorted unique ints."""
    cores: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            cores.extend(range(int(a), int(b) + 1))
        else:
            cores.append(int(part))
    return sorted(set(cores))


def _env_core_list(name: str, default: str) -> list[int]:
    return _parse_core_list(os.getenv(name, default).strip() or default)


@dataclass(slots=True)
class LocalityPlan:
    """Resolved locality plan for the current host."""

    mode: str  # numa_aware | cache_aware | off
    numa_nodes: int
    multi_node: bool
    core_partitions: dict[str, list[int]] = field(default_factory=dict)
    cpuset_strings: dict[str, str] = field(default_factory=dict)
    omp: dict[str, str] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def cores_for(self, role: str) -> list[int]:
        """role: draft|verify|tier1|tier2|tier3|gateway"""
        key = role.lower()
        if key in {"draft", "prefill"}:
            return list(self.core_partitions.get("tier1") or [])
        if key in {"verify", "verifier", "decode"}:
            t2 = self.core_partitions.get("tier2") or []
            t3 = self.core_partitions.get("tier3") or []
            return sorted(set(t2) | set(t3))
        return list(self.core_partitions.get(key) or [])


def default_uma_partitions(n_cores: int) -> dict[str, list[int]]:
    """Build draft/verifier partitions for a homogeneous single-UMA host."""
    cores = list(range(max(1, n_cores)))
    if len(cores) <= 2:
        return {"tier1": cores[:], "tier2": cores[:], "tier3": cores[:]}
    if len(cores) <= 4:
        mid = max(1, len(cores) // 2)
        return {
            "tier1": cores[:mid],
            "tier2": cores[mid:],
            "tier3": cores[mid:],
        }
    # 8-core Axion (and similar): 2 + 3 + 3
    draft_n = min(2, len(cores) // 4 or 1)
    remain = cores[draft_n:]
    half = (len(remain) + 1) // 2
    return {
        "tier1": cores[:draft_n],
        "tier2": remain[:half],
        "tier3": remain[half:] or remain[-1:],
    }


def resolve_locality_plan(
    *,
    numa_nodes: int,
    online_cores: Sequence[int] | None = None,
    multi_node: bool | None = None,
) -> LocalityPlan:
    """Select NUMA-aware vs cache-aware locality for the current topology."""
    cores = list(online_cores) if online_cores is not None else list(range(8))
    if not cores:
        cores = [0]
    n_nodes = max(1, int(numa_nodes))
    is_multi = bool(multi_node) if multi_node is not None else n_nodes > 1
    mode_env = locality_mode_env()

    omp = {
        "OMP_PROC_BIND": os.getenv("OMP_PROC_BIND", "close"),
        "OMP_PLACES": os.getenv("OMP_PLACES", "cores"),
    }

    if mode_env == "off":
        return LocalityPlan(
            mode="off",
            numa_nodes=n_nodes,
            multi_node=is_multi,
            reason="NSA_LOCALITY_MODE=off — OS default scheduling.",
            omp=omp,
        )

    # Explicit numa mode still cannot invent nodes on single-UMA.
    want_numa = mode_env == "numa" or (mode_env == "auto" and is_multi)
    if want_numa and is_multi:
        # Node-level placement; still expose empty core partitions (numactl owns it).
        return LocalityPlan(
            mode="numa_aware",
            numa_nodes=n_nodes,
            multi_node=True,
            reason=(
                "Multi-NUMA topology: draft/verifier use topology-gated numactl "
                "cpunodebind/membind (see bind_planned)."
            ),
            omp=omp,
        )

    # Cache-aware / single-UMA path (Axion C4A and force uma_affinity).
    defaults = default_uma_partitions(len(cores))
    draft_default = _fmt_range(defaults["tier1"])
    draft_cpus = (os.getenv("NSA_DRAFT_CPUSET") or os.getenv("NSA_TIER1_CPUSET") or draft_default).strip()
    verify_cpus = (os.getenv("NSA_VERIFY_CPUSET") or "").strip()
    if verify_cpus:
        verify_list = _parse_core_list(verify_cpus)
        # Split verify pool: first half → tier2, rest → tier3 (or TIER3 override).
        mid = max(1, (len(verify_list) + 1) // 2)
        tier2_list = verify_list[:mid]
        tier3_override = (os.getenv("NSA_TIER3_CPUSET") or "").strip()
        tier3_list = _parse_core_list(tier3_override) if tier3_override else verify_list[mid:] or verify_list[-1:]
        parts = {
            "tier1": _parse_core_list(draft_cpus),
            "tier2": tier2_list,
            "tier3": tier3_list,
        }
    else:
        parts = {
            "tier1": _parse_core_list(draft_cpus),
            "tier2": _env_core_list("NSA_TIER2_CPUSET", _fmt_range(defaults["tier2"])),
            "tier3": _env_core_list("NSA_TIER3_CPUSET", _fmt_range(defaults["tier3"])),
        }
    # Clamp to online cores.
    online = set(int(c) for c in cores)
    for k, v in list(parts.items()):
        clamped = [c for c in v if c in online]
        parts[k] = clamped or sorted(online)[: max(1, len(v) or 1)]

    cpusets = {k: _fmt_range(v) for k, v in parts.items()}
    reason = (
        "Single-UMA / Axion path: cache-aware CPU affinity "
        f"(draft={cpusets['tier1']}, verifier tier2={cpusets['tier2']}, "
        f"tier3={cpusets['tier3']}). Cross-NUMA split is not applicable."
    )
    if mode_env == "numa" and not is_multi:
        reason += " NSA_LOCALITY_MODE=numa ignored (numa_nodes==1)."

    return LocalityPlan(
        mode="cache_aware",
        numa_nodes=n_nodes,
        multi_node=False,
        core_partitions=parts,
        cpuset_strings=cpusets,
        omp=omp,
        reason=reason,
    )


def _fmt_range(cores: Sequence[int]) -> str:
    """Compact cores to docker cpuset string (e.g. 0-1, 2-4)."""
    xs = sorted({int(c) for c in cores})
    if not xs:
        return "0"
    ranges: list[str] = []
    start = prev = xs[0]
    for c in xs[1:]:
        if c == prev + 1:
            prev = c
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = c
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)


def taskset_argv(cores: Sequence[int]) -> list[str] | None:
    """Optional taskset prefix for ProcessSupervisor on single-UMA hosts."""
    if not cores:
        return None
    return ["taskset", "-c", _fmt_range(cores)]


def build_affinity_prefix(
    *,
    tier: int | str,
    plan: LocalityPlan,
    numa_bind: Sequence[str] | None = None,
) -> list[str] | None:
    """Prefix command with numactl (multi) or taskset (single-UMA cache-aware)."""
    if numa_bind:
        return list(numa_bind)
    if plan.mode != "cache_aware":
        return None
    if isinstance(tier, str):
        digits = "".join(ch for ch in tier if ch.isdigit())
        name = tier if tier.startswith("tier") else f"tier{digits or 1}"
    else:
        name = f"tier{int(tier)}"
    cores = plan.core_partitions.get(name) or []
    return taskset_argv(cores)
