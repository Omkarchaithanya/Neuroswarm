# Linux perf + eBPF profiling (Axion / llama.cpp)

Open-source PMU and operator-level profiling for Kleidi `llama-server` on Axion.
This is the **stock `perf` + `bpftrace`** path — not Arm Performix and not ProfInfer.

**ProfInfer** ([arXiv:2601.20755](https://arxiv.org/abs/2601.20755)) describes eBPF + llama.cpp operator tracing but has **no public installable release**. NeuroSwarm implements the same capability class with tools that ship on Ubuntu/Axion today.

## Install (host)

On the Axion VM (privileged):

```bash
bash scripts/install-host-profilers.sh
```

Installs `linux-tools-*`, `bpftrace`, and prints a sample of Arm/SVE/NEON events from `perf list`.

Check:

```bash
perf version
bpftrace --version
cat /proc/sys/kernel/perf_event_paranoid
```

Attaching PMU counters to another PID often needs `perf_event_paranoid <= 1` or `sudo`.
`scripts/install-host-profilers.sh` sets `kernel.perf_event_paranoid=1` when possible.

## Capture under chat load

Prefer DeepSeek / tier3 `llama-server` PID (same honesty as Performix: never idle system-wide).

```bash
# Resolve PID (optional — scripts auto-detect)
export NSA_PERF_PID=$(pgrep -af 'DeepSeek-R1|7B-Q4' | awk '/llama-server/{print $1; exit}')

PERF_DURATION=20 bash scripts/capture-linux-perf.sh
EBPF_DURATION=15 bash scripts/capture-ebpf-llamacpp.sh
```

Artifacts land under `work/profiling/`:

| File | Meaning |
|------|---------|
| `perf-summary.json` | `source=linux_perf`, IPC, event counts, `sve_events_used` |
| `perf-stat-*.txt` | Raw `perf stat` |
| `perf-report-*.txt` | `perf report --stdio` (if record succeeded) |
| `ebpf-llamacpp-summary.json` | `source=ebpf_bpftrace` **or** honest `ebpf_unavailable` |

### Reading SVE / NEON / PMU

- If Neoverse exposes SVE/ASE **hardware** events (`/sys/bus/event_source/devices/armv8_pmuv3*`), `sve_events_used` is non-empty and `hardware_pmu_available=1`.
- Some GCP Axion images expose **only software** events (`task-clock`, `cpu-clock`, …). Then `event_mode=software`, `hardware_pmu_available=0`, and IPC stays 0 — that is **honest**, not a failed capture (look for non-zero `task-clock` / `nonzero_event_count`).
- Empty `sve_events_used` with HW PMU present is also honest when those specific events are missing.

### eBPF modes

1. **uprobes** — symbols found via `nm -D` / `readelf` on `/proc/$PID/exe` (`ggml_graph_compute`, `llama_decode`, …).
2. **oncpu_fallback** — stripped binary: `profile:hz` stacks for that PID only.
3. **ebpf_unavailable** — missing bpftrace, CAP_BPF, or attach failure (reason in JSON).

## In-process RPF providers

| Env | Effect |
|-----|--------|
| `NSA_PERF_PID` | `PerfProfilerProvider` + `LinuxPerfProvider` attach to this PID |
| `NSA_EBPF_PROFILE=1` | `EbpfProfilerProvider` runs short bpftrace samples |
| `NSA_EBPF_BINARY` | Optional explicit path to `llama-server` ELF |

```bash
export NSA_PERF_PID=...
export NSA_EBPF_PROFILE=1
export NSA_RPF_PROVIDER=perf   # or auto
```

Metrics include `hardware.ipc`, `hardware.sve_inst_retired`, `hardware.sve_events_available`, and `ebpf.op.*` hit counts when uprobes work.

## vs Arm Performix

| | Linux perf / bpftrace | Arm Performix (`apx`) |
|--|----------------------|------------------------|
| License | Open | Closed |
| Flame / hotspots | `perf record` files | GUI / recipe JSON |
| Operator counters | bpftrace uprobes | Recipe-dependent |
| Honesty | Empty SVE list if no events | `pmu_available` flag |

Keep Performix for GUI/recipes; use this path for CI-friendly, open tooling.

## Grafana

Dashboard **Linux Profiling** (`neuroswarm-linux-profiling`) charts gateway `profile_*` gauges (IPC, cycles, SVE availability) when RPF is active. Flamegraphs and bpftrace dumps remain files under `work/profiling/` — not PromQL.

See also: [provider-guide.md](provider-guide.md), [host-monitoring.md](../observability/host-monitoring.md), [performix-gui-windows.md](../telemetry/performix-gui-windows.md).
