"""NUMA topology truth — honest status for Axion (single UMA) and multi-node hosts.

GCP C4A is a single UMA domain: cross-NUMA penalties are not applicable when
the guest reports one NUMA node. Multi-node bind (numactl / llama --numa) is
gated and only planned when nodes > 1.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .cpu_topology import read_numa_topology, read_online_cpus


def _env_truthy(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def numa_policy_env() -> str:
    """Return NSA_NUMA_POLICY: auto | off | force (default auto)."""
    raw = (os.getenv("NSA_NUMA_POLICY") or "auto").strip().lower()
    if raw in {"auto", "off", "force"}:
        return raw
    return "auto"


def _read_machine_type() -> str | None:
    """Best-effort GCE metadata machine type (Axion SSH / in-guest only)."""
    url = (
        "http://metadata.google.internal/computeMetadata/v1/instance/machine-type"
    )
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
            return text.rsplit("/", 1)[-1] if text else None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _process_mempolicy_bound() -> bool:
    """True if current process has a non-default NUMA mempolicy (Linux)."""
    path = Path(f"/proc/{os.getpid()}/numa_maps")
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    # Default policy lines typically lack bind=/interleave= markers on anon maps.
    for line in text.splitlines():
        if " bind:" in line or " interleave:" in line or " prefer:" in line:
            return True
    return False


def build_numa_bind_argv(
    *,
    tier: int | str,
    nodes: Sequence[int],
    policy: str | None = None,
) -> list[str] | None:
    """Build numactl prefix for a tier process, or None when bind must not run.

    Rules:
    - nodes <= 1 → always None (Axion / single UMA); force does not invent nodes
    - policy off → None
    - policy auto → bind when NSA_NUMA_BIND is unset/true and nodes > 1
    - policy force → same as auto when nodes > 1; None when nodes <= 1
    """
    node_ids = sorted({int(n) for n in nodes})
    if len(node_ids) <= 1:
        return None
    pol = (policy or numa_policy_env()).lower()
    if pol == "off":
        return None
    if pol == "auto" and os.getenv("NSA_NUMA_BIND", "1").strip() not in {
        "",
        "1",
        "true",
        "TRUE",
        "yes",
        "on",
    }:
        return None
    # Map tier → node (clamp to available nodes).
    if isinstance(tier, str):
        digits = "".join(ch for ch in tier if ch.isdigit())
        tier_n = int(digits) if digits else 1
    else:
        tier_n = int(tier)
    # tier1/drafter → first node; tier2+ → second (or last) node
    if tier_n <= 1:
        node = node_ids[0]
    else:
        node = node_ids[min(1, len(node_ids) - 1)]
    return [
        "numactl",
        f"--cpunodebind={node}",
        f"--membind={node}",
    ]


def llama_numa_flag(nodes: Sequence[int], policy: str | None = None) -> str | None:
    """llama.cpp --numa mode when process is node-pinned; None on single UMA."""
    if build_numa_bind_argv(tier=1, nodes=nodes, policy=policy) is None:
        return None
    return "isolate"


@dataclass(slots=True)
class NumaStatus:
    numa_nodes: int
    cpulists: dict[str, list[int]] = field(default_factory=dict)
    multi_node: bool = False
    memory_bind_active: bool = False
    cross_numa_penalty_applicable: bool = False
    policy: str = "single_uma"
    machine_type: str | None = None
    numa_policy_env: str = "auto"
    bind_planned: dict[str, list[str] | None] = field(default_factory=dict)
    llama_numa: str | None = None
    reason: str = ""
    # Dual-mode locality (cache-aware on Axion; NUMA when multi-node)
    locality_mode: str = "cache_aware"
    core_partitions: dict[str, list[int]] = field(default_factory=dict)
    cpuset_strings: dict[str, str] = field(default_factory=dict)
    omp: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def collect_numa_status(
    *,
    topology: Mapping[int, list[int]] | None = None,
    machine_type: str | None = None,
    memory_bind_active: bool | None = None,
) -> NumaStatus:
    """Build honest NUMA + locality status for health/probe/metrics."""
    from .locality_scheduler import resolve_locality_plan

    topo = dict(topology) if topology is not None else read_numa_topology()
    if not topo:
        topo = {0: read_online_cpus()}
    node_ids = sorted(topo.keys())
    n = len(node_ids)
    multi = n > 1
    cpulists = {str(k): list(v) for k, v in sorted(topo.items())}
    pol_env = numa_policy_env()
    mt = machine_type if machine_type is not None else _read_machine_type()
    mem_active = (
        bool(memory_bind_active)
        if memory_bind_active is not None
        else _process_mempolicy_bound()
    )

    online: list[int] = []
    for cpus in topo.values():
        online.extend(int(c) for c in cpus)
    online = sorted(set(online)) or read_online_cpus()

    locality = resolve_locality_plan(
        numa_nodes=n, online_cores=online, multi_node=multi
    )

    bind_planned: dict[str, list[str] | None] = {}
    for tier_name in ("tier1", "tier2", "tier3"):
        bind_planned[tier_name] = build_numa_bind_argv(
            tier=tier_name, nodes=node_ids, policy=pol_env
        )
    llama = llama_numa_flag(node_ids, policy=pol_env)
    any_bind = any(v is not None for v in bind_planned.values())

    if not multi:
        policy = "single_uma"
        reason = (
            "Guest reports 1 NUMA node (GCP C4A / Axion is a single UMA domain). "
            "Cross-NUMA penalties are not applicable; using cache-aware CPU affinity "
            f"({locality.cpuset_strings})."
        )
        if pol_env == "force":
            reason += " NSA_NUMA_POLICY=force ignored because nodes==1."
    elif any_bind:
        policy = "numa_bind_active" if mem_active else "numa_split_ready"
        reason = (
            "Multi-NUMA topology detected; numactl cpunodebind/membind planned per tier "
            f"(llama --numa {llama})."
        )
        if mem_active:
            policy = "numa_bind_active"
            reason = "Multi-NUMA topology; process mempolicy indicates bind/interleave active."
    else:
        policy = "numa_split_ready"
        reason = (
            "Multi-NUMA topology detected but bind disabled "
            f"(NSA_NUMA_POLICY={pol_env} / NSA_NUMA_BIND)."
        )

    if locality.reason and not multi:
        reason = locality.reason
        if pol_env == "force":
            reason += " NSA_NUMA_POLICY=force ignored because nodes==1."

    return NumaStatus(
        numa_nodes=n,
        cpulists=cpulists,
        multi_node=multi,
        memory_bind_active=mem_active,
        cross_numa_penalty_applicable=multi,
        policy=policy,
        machine_type=mt,
        numa_policy_env=pol_env,
        bind_planned=bind_planned,
        llama_numa=llama,
        reason=reason,
        locality_mode=locality.mode,
        core_partitions=locality.core_partitions,
        cpuset_strings=locality.cpuset_strings,
        omp=locality.omp,
    )


def publish_numa_metrics(registry: Any, status: NumaStatus | None = None) -> NumaStatus:
    """Set neuroswarm_* / nexus_* NUMA gauges on an RMF registry."""
    st = status or collect_numa_status()
    labels = {"topology": st.policy}
    try:
        registry.set("neuroswarm_numa_nodes", float(st.numa_nodes), labels=labels)
        registry.set(
            "neuroswarm_cross_numa_applicable",
            1.0 if st.cross_numa_penalty_applicable else 0.0,
            labels=labels,
        )
        registry.set(
            "neuroswarm_numa_bind_planned",
            1.0 if any(st.bind_planned.values()) else 0.0,
            labels=labels,
        )
        # Canonical nexus_* aliases for catalogue consumers
        registry.set("nexus_hw_numa_nodes", float(st.numa_nodes), labels=labels)
        registry.set(
            "nexus_hw_cross_numa_applicable",
            1.0 if st.cross_numa_penalty_applicable else 0.0,
            labels=labels,
        )
    except Exception:
        pass
    return st
