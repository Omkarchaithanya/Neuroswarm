"""Pillar 1 — NUMA topology verification benchmark for Cascade."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from neuroswarm_arm.config import get_config

DEFAULT_RESULTS_PATH = REPO_ROOT / "benchmarks" / "results" / "numa_verify.json"

LOG = logging.getLogger("numa_verify")

_NODE_COUNT_RE = re.compile(r"available:\s+(\d+)\s+nodes?", re.IGNORECASE)
_TASKSET_MASK_RE = re.compile(r"mask:\s*([0-9a-fx,]+)", re.IGNORECASE)
_LLAMA_CMD_HINTS = ("llama-server", "llama.cpp", "llama_cli", "server")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_numactl_hardware() -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["numactl", "--hardware"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        return None, "numactl not found on PATH"
    except OSError as exc:
        return None, str(exc)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        return None, err
    return proc.stdout, None


def parse_numa_node_count(hardware_text: str) -> int:
    match = _NODE_COUNT_RE.search(hardware_text)
    if match:
        return max(1, int(match.group(1)))
    nodes = [line for line in hardware_text.splitlines() if line.strip().lower().startswith("node ")]
    return max(1, len(nodes))


def sysfs_numa_node_count() -> int | None:
    sysfs = Path("/sys/devices/system/node")
    if not sysfs.is_dir():
        return None
    nodes = [p.name for p in sysfs.iterdir() if p.name.startswith("node") and p.name[4:].isdigit()]
    return max(1, len(nodes)) if nodes else 1


def tier_url_map() -> dict[str, str]:
    cfg = get_config()
    return {
        "tier1": cfg.tier1_url,
        "tier2": cfg.tier2_url,
        "tier3": cfg.tier3_url,
    }


def resolve_tier_url(url: str, timeout: float = 5.0) -> dict[str, Any]:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return {"url": url, "resolved": False, "error": "missing hostname"}

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    result: dict[str, Any] = {"url": url, "host": host, "port": port}
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        result["resolved"] = True
        result["addresses"] = sorted({info[4][0] for info in infos})
    except OSError as exc:
        result["resolved"] = False
        result["error"] = str(exc)
        return result

    base = url.rstrip("/")
    for path in ("/health", "/v1/models"):
        probe = f"{base}{path}"
        try:
            req = Request(probe, method="GET")
            with urlopen(req, timeout=timeout) as resp:
                result["http_ok"] = True
                result["http_probe"] = probe
                result["http_status"] = getattr(resp, "status", 200)
                break
        except (URLError, OSError, TimeoutError) as exc:
            result.setdefault("http_errors", []).append({path: str(exc)})
    else:
        result["http_ok"] = False
    return result


def _read_proc_status_field(pid: int, prefix: str) -> str | None:
    status_path = Path(f"/proc/{pid}/status")
    if not status_path.is_file():
        return None
    try:
        for line in status_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def taskset_affinity(pid: int) -> dict[str, Any]:
    info: dict[str, Any] = {"pid": pid, "obtained": False}
    try:
        proc = subprocess.run(
            ["taskset", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            text = (proc.stdout or "").strip()
            info["taskset"] = text
            match = _TASKSET_MASK_RE.search(text)
            if match:
                info["cpu_mask"] = match.group(1)
            info["obtained"] = True
            return info
        info["taskset_error"] = (proc.stderr or proc.stdout or "").strip()
    except FileNotFoundError:
        info["taskset_error"] = "taskset not found on PATH"
    except OSError as exc:
        info["taskset_error"] = str(exc)

    cpus = _read_proc_status_field(pid, "Cpus_allowed_list:")
    if cpus:
        info["cpus_allowed_list"] = cpus
        info["obtained"] = True
    return info


def _hex_port(port: int) -> str:
    return format(port, "X")


def pid_for_listening_port(port: int) -> int | None:
    tcp_path = Path("/proc/net/tcp")
    tcp6_path = Path("/proc/net/tcp6")
    targets = {_hex_port(port)}

    def scan_table(path: Path, ipv6: bool) -> int | None:
        if not path.is_file():
            return None
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]
        except OSError:
            return None
        for line in lines:
            parts = line.split()
            if len(parts) < 10:
                continue
            local = parts[1]
            state = parts[3]
            inode = parts[9]
            if state != "0A":
                continue
            host_hex, port_hex = local.split(":")
            if port_hex.upper() not in targets:
                continue
            if ipv6 and host_hex != "00000000000000000000000000000000":
                continue
            if not ipv6 and host_hex not in {"00000000", "0100007F"}:
                # best-effort: accept 0.0.0.0 and 127.0.0.1 listeners
                continue
            for proc_dir in Path("/proc").iterdir():
                if not proc_dir.name.isdigit():
                    continue
                fd_dir = proc_dir / "fd"
                if not fd_dir.is_dir():
                    continue
                try:
                    for fd in fd_dir.iterdir():
                        try:
                            target = os.readlink(fd)
                        except OSError:
                            continue
                        if f"socket:[{inode}]" in target:
                            return int(proc_dir.name)
                except OSError:
                    continue
        return None

    return scan_table(tcp_path, ipv6=False) or scan_table(tcp6_path, ipv6=True)


def find_llama_pid_for_tier(tier: str, url: str) -> int | None:
    parsed = urlparse(url)
    port = parsed.port or 80

    by_port = pid_for_listening_port(port)
    if by_port is not None and _looks_like_llama(by_port):
        return by_port

    host_hint = (parsed.hostname or "").lower()
    tier_hint = tier.lower()
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        pid = int(proc_dir.name)
        cmdline_path = proc_dir / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        cmd = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
        if not any(hint in cmd for hint in _LLAMA_CMD_HINTS):
            continue
        if tier_hint in cmd or host_hint in cmd or f":{port}" in cmd or f" {port}" in cmd:
            return pid
    return by_port


def _looks_like_llama(pid: int) -> bool:
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        raw = cmdline_path.read_bytes()
    except OSError:
        return False
    cmd = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").lower()
    return any(hint in cmd for hint in _LLAMA_CMD_HINTS)


def proc_numa_binding(pid: int) -> dict[str, Any]:
    info: dict[str, Any] = {"pid": pid, "obtained": False}

    mems = _read_proc_status_field(pid, "Mems_allowed_list:")
    cpus = _read_proc_status_field(pid, "Cpus_allowed_list:")
    if mems:
        info["mems_allowed_list"] = mems
    if cpus:
        info["cpus_allowed_list"] = cpus

    numa_maps = Path(f"/proc/{pid}/numa_maps")
    if numa_maps.is_file():
        try:
            text = numa_maps.read_text(encoding="utf-8", errors="ignore")
            nodes = sorted({int(m.group(1)) for m in re.finditer(r"N(\d+)=", text)})
            if nodes:
                info["numa_maps_nodes"] = nodes
                info["obtained"] = True
        except OSError:
            pass

    try:
        proc = subprocess.run(
            ["numastat", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            info["numastat"] = proc.stdout.strip()
            info["obtained"] = True
    except FileNotFoundError:
        info["numastat_error"] = "numastat not found on PATH"
    except OSError as exc:
        info["numastat_error"] = str(exc)

    if mems and mems not in {"0", "0-0"} and "-" not in mems and "," not in mems:
        try:
            info["inferred_numa_node"] = int(mems)
            info["obtained"] = True
        except ValueError:
            pass

    return info


def verify_single_node(tier_urls: dict[str, str]) -> dict[str, Any]:
    LOG.info(
        "NUMA-split drafter/verifier requires multi-NUMA hardware; "
        "single-node fallback — verifying tier URL reachability and CPU affinity"
    )
    tiers: dict[str, Any] = {}
    for tier, url in tier_urls.items():
        entry: dict[str, Any] = {"url_check": resolve_tier_url(url)}
        pid = find_llama_pid_for_tier(tier, url)
        if pid is not None:
            entry["pid"] = pid
            entry["cpu_affinity"] = taskset_affinity(pid)
        else:
            entry["cpu_affinity"] = {"obtained": False, "note": "llama-server pid not found"}
        tiers[tier] = entry

    return {
        "status": "single_node_fallback",
        "note": (
            "NUMA-split drafter/verifier requires multi-NUMA hardware; "
            "verified tier endpoints and best-effort CPU affinity instead"
        ),
        "tiers": tiers,
    }


def verify_multi_node(tier_urls: dict[str, str]) -> dict[str, Any]:
    tiers: dict[str, Any] = {}
    bindings: list[int | None] = []
    any_pid = False
    all_binding_obtained = True

    for tier, url in tier_urls.items():
        entry: dict[str, Any] = {"url": url, "url_check": resolve_tier_url(url)}
        pid = find_llama_pid_for_tier(tier, url)
        if pid is None:
            entry["pid"] = None
            entry["numa_binding"] = {
                "obtained": False,
                "note": "llama-server pid not inspectable (container/host boundary?)",
            }
            all_binding_obtained = False
            bindings.append(None)
        else:
            any_pid = True
            entry["pid"] = pid
            binding = proc_numa_binding(pid)
            entry["numa_binding"] = binding
            if not binding.get("obtained"):
                all_binding_obtained = False
            node = binding.get("inferred_numa_node")
            if node is None:
                nodes = binding.get("numa_maps_nodes")
                if isinstance(nodes, list) and len(nodes) == 1:
                    node = nodes[0]
            bindings.append(node if isinstance(node, int) else None)
            if node is None:
                all_binding_obtained = False
        tiers[tier] = entry

    distinct_nodes = {n for n in bindings if n is not None}
    if all_binding_obtained and len(distinct_nodes) >= 2:
        status = "multi_node_available"
        note = "Multi-NUMA topology present; tier llama-server bindings observed"
    else:
        status = "topology_present_binding_unverified"
        if not any_pid:
            note = (
                "Multi-NUMA topology present but tier llama-server NUMA bindings "
                "could not be verified without container introspection"
            )
        else:
            note = (
                "Multi-NUMA topology present; partial or ambiguous per-tier NUMA binding"
            )

    return {
        "status": status,
        "note": note,
        "distinct_numa_nodes_observed": sorted(distinct_nodes),
        "tiers": tiers,
    }


def run_numa_verify(*, results_path: Path = DEFAULT_RESULTS_PATH) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    payload: dict[str, Any] = {
        "pillar": "pillar_1_numa_verify",
        "tier_urls": tier_url_map(),
    }

    hardware_text, hardware_err = run_numactl_hardware()
    if hardware_text is None:
        payload.update(
            {
                "status": "numactl_unavailable",
                "error": hardware_err,
                "sysfs_numa_node_count": sysfs_numa_node_count(),
            }
        )
        write_json(results_path, payload)
        LOG.warning("numactl unavailable: %s", hardware_err)
        return payload

    node_count = parse_numa_node_count(hardware_text)
    payload["numa_node_count"] = node_count
    payload["numactl_hardware"] = hardware_text.strip()

    sysfs_count = sysfs_numa_node_count()
    if sysfs_count is not None:
        payload["sysfs_numa_node_count"] = sysfs_count

    tier_urls = tier_url_map()
    if node_count <= 1:
        payload.update(verify_single_node(tier_urls))
    else:
        payload.update(verify_multi_node(tier_urls))

    write_json(results_path, payload)
    LOG.info("wrote %s status=%s", results_path, payload["status"])
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Pillar 1 NUMA topology verification benchmark")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_RESULTS_PATH),
        help="Output JSON path (default: benchmarks/results/numa_verify.json)",
    )
    args = parser.parse_args()
    run_numa_verify(results_path=Path(args.out))


if __name__ == "__main__":
    main()
