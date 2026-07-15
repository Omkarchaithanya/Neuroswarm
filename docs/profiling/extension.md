# Extension Guide

Alias of [plugin-guide.md](plugin-guide.md).

Extension points:

1. **Profilers** — new HW/OS collectors
2. **Exporters** — new sinks (Parca push, custom warehouses)
3. **Report builders** — alternate `RuntimeProfile` shaping
4. **Metric sources** — peer scrapes into RPF telemetry
5. **Dashboards** — Grafana panel descriptors via `register_dashboard`

Peers (DIPA/HAOE/MAKS/AQR/AWPP) extend via **connectors only** (`ProfileSignalBus` / `PhaseSignalConnector`) — never import provider concretes.
