# Host monitoring (htop / btop / Glances / cAdvisor)

Real OS and container stats for NeuroSwarm Axion — no demo or synthetic series.

## Layers

| Layer | Tool | Where | What you get |
|-------|------|-------|----------------|
| Human TUI | `htop` / `btop` | Axion host SSH | Full Neoverse host view (`/proc`) |
| Human TUI | `htop` / `btop` | `docker compose exec gateway …` | Gateway container PID namespace only |
| HTTP / JSON | Glances | `:61208` on Axion | Web UI + `/api/4/*` |
| Prometheus | Glances exporter | `:61209` → obs scrape | Host CPU / mem / load |
| Prometheus | cAdvisor | `:8088` → obs scrape | Per-container CPU / mem |

## Install host TUIs (Axion)

```bash
cd ~/neuroswarm-arm
bash scripts/install-host-monitors.sh
htop    # or: btop
```

## Gateway image TUIs

After rebuilding the gateway image (`Dockerfile.arm64` / `Dockerfile.gateway` include htop + btop):

```bash
docker compose exec gateway htop
docker compose exec gateway btop
```

For a **host-wide** view from a one-off container (does not change the default gateway):

```bash
docker compose run --rm --pid=host --privileged gateway btop
```

## Sidecars (compose profile `hostmon`)

```bash
cd ~/neuroswarm-arm
docker compose --profile hostmon up -d cadvisor glances glances-web

curl -sS http://127.0.0.1:8088/metrics | head
curl -sS http://127.0.0.1:61209/metrics | head
curl -sS http://127.0.0.1:61208/api/4/cpu | head -c 400
```

Note: Glances cannot run `--export prometheus` in the same process as `-w` web mode, so compose runs **`glances`** (quiet Prometheus exporter on host `:61209`) and **`glances-web`** (UI/JSON on `:61208`) as two services.

Also keep **cAdvisor** on `:8088` for raw cgroup series; named Docker CPU/mem in Grafana prefer **Glances** `glances_containers_*` (cAdvisor on newer Docker may need `DOCKER_API_VERSION=1.44`).

Env notes: [`.env.example`](../../.env.example) (`NSA_GLANCES_URL`, port list). Restrict `:8088` / `:61208` / `:61209` with VPC firewall to the obs subnet when possible.

## Obs Prometheus

[`ops/prometheus.obs.yml`](../../ops/prometheus.obs.yml) scrapes:

- `10.128.0.2:8088` — cAdvisor
- `10.128.0.2:61209` — Glances Prometheus exporter

After updating the file on `neuroswarm-obs`, reload Prometheus (restart the compose Prometheus service or `/-/reload` if enabled).

## Grafana

Dashboard: **NeuroSwarm System Resources**  
UID: `neuroswarm-system-resources`  
File: [`ops/grafana/dashboards/system-resources.json`](../grafana/dashboards/system-resources.json)

Via tunnel (same pattern as Latency & Tokens):

`http://127.0.0.1:13000/grafana/d/neuroswarm-system-resources/neuroswarm-system-resources?orgId=1&refresh=5s`

**Empty panels mean:** scrape down, tunnel down, or `hostmon` not started — not dummy zeros. Values only move when the host/containers are under real load.

## Glances UI tunnel (optional)

```text
putty -ssh -i ~/.ssh/google_compute_engine.ppk -N \
  -L 161208:127.0.0.1:61208 tejaswini2482_gmail_com@<axion-nat>
```

Then open `http://127.0.0.1:161208/`.

## Out of scope (this pass)

- ArmPMU `perf_event_open` rewrite
- RTG `host_pressure` budget cuts
- `neuroswarm top` CLI
