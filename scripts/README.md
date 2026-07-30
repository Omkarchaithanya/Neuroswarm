# Deployment Scripts

## One-command sync + deploy (preferred)

From Windows (repo root), with gcloud on PATH:

```powershell
# Compose on neuroswarm-axion (default)
powershell -ExecutionPolicy Bypass -File scripts\sync-and-deploy.ps1 -Mode compose

# k3s + Helm on neuroswarm-axion (stops Compose gateway/tiers on conflicting ports)
powershell -ExecutionPolicy Bypass -File scripts\sync-and-deploy.ps1 -Mode k8s

# Flags: -SkipSync, -SkipBuild, -Performix (compose profile), -Smoke, -RequireHealth:$false
powershell -ExecutionPolicy Bypass -File scripts\sync-and-deploy.ps1 -Mode k8s -RequireHealth -Smoke
```

This runs `sync-vm.ps1 -PreferGcloud`, then remote `scripts/remote-compose-up.sh` or `install-k3s-axion.sh` + `remote-helm-up.sh`. Health probes **fail the deploy** by default (`REQUIRE_HEALTH=1`). No manual SCP/pip required.

After k8s mode, API is typically on NodePort **30080** (`curl http://<axion-ip>:30080/health`). Point obs Prometheus at `10.128.0.2:30080/metrics` if you leave Compose nginx down.

**Compose + k3s coexistence:** k3s Traefik LoadBalancer binds host `:80` and wins for `127.0.0.1/health` (Go `404 page not found`). `scripts/free-host-port80-for-compose.sh` scales Traefik to 0 so Compose nginx can own `:80`. Helm/API stays on NodePort **30080**. Set `KEEP_TRAEFIK=1` to skip.

## Docker Compose (local / Axion ARM64)

```bash
cp .env.example .env   # Windows: Copy-Item .env.example .env
# MUST use KleidiAI image — never leave stock llama.cpp for evidence:
#   bash scripts/deploy-kleidiai-tiers.sh
docker compose --compatibility up --build -d
curl -fsS http://127.0.0.1/health
curl -fsS http://127.0.0.1:8000/ready
bash scripts/capture-evidence.sh
bash performix_capture.sh          # Arm Performix (apx)
bash scripts/verify-mcp-templates.sh
bash scripts/verify-sglang-arm64.sh  # before pd-profile claims
```

Stack: nginx proxy public `:80` → gateway API. Prometheus + Grafana run on **neuroswarm-obs** (`docker-compose.obs.yaml`). OTEL collector on axion remote_writes metrics. Paths on obs: `/prometheus/`, `/grafana/`.

### Re-host stack on Axion VM

Prefer `sync-and-deploy.ps1 -Mode compose`. Manual equivalent:

```bash
cd ~/neuroswarm-arm
bash scripts/remote-compose-up.sh
```

### Observability host (neuroswarm-obs)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-obs-vm.ps1 `
  -ProjectId <project> -SourceRanges <your-ip>/32
# Sync repo to obs VM, then:
docker compose -f docker-compose.obs.yaml --compatibility up -d
```

Grafana: `http://<obs-external-ip>/grafana/` (Arm Performix Overview dashboard).

### Arm Performix on Axion

**Primary path (required for Neuroswarm):** run `apx` **on the Axion host**, not the Windows desktop GUI.

```bash
bash scripts/install-performix.sh          # .deb + symlink; apx target prepare (0-arg only)
# Recipe flow (current CLI — no --output / --binary):
#   apx target prepare
#   apx recipe run code_hotspots --system-wide --timeout 60 --deploy-tools --json
#   apx run export <run_id> <dir> --json
#   python3 scripts/performix_normalize_export.py …
NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 PERFORMIX_DURATION=60 \
  bash scripts/refresh-performix-snapshot.sh   # → work/performix/snapshot.json source=apx|unavailable
# Live updates (host cron — apx lives on the VM, not inside the gateway container):
(crontab -l 2>/dev/null; echo "*/2 * * * * cd \$HOME/neuroswarm-arm && NSA_PERFORMIX_ALLOW_DEMO=0 bash scripts/refresh-performix-snapshot.sh >>work/performix/refresh.log 2>&1") | crontab -
# Product MCP = HTTP performix-bridge wrapping host apx (preferred over Arm MCP stdio image):
export NSA_AROP_PERFORMIX_MCP=http://performix-bridge:8090
docker compose --profile performix up -d --build gateway performix-bridge
# Optional official Arm MCP image (stdio / IDE only; not the AROP HTTP path):
docker compose --profile performix up -d arm-mcp
# Trigger AROP collect (uses bridge when NSA_AROP_PERFORMIX_MCP is set):
curl -fsS -X POST http://127.0.0.1/arop/optimize -H 'Content-Type: application/json' -d '{"force":true}'
```

**Windows Performix GUI (optional):** Not required for Grafana/`source=apx`. Install for interactive exploration — see [`docs/telemetry/performix-gui-windows.md`](../docs/telemetry/performix-gui-windows.md): Targets → SSH to `neuroswarm-axion` (`104.198.180.95`) → attach live `llama-server` → Code Hotspots. Automation does not ingest GUI results unless you manually export into `work/performix/`.

**Official Arm MCP** ([arm/mcp](https://github.com/arm/mcp), image `armlimited/arm-mcp`): IDE assistant toolbox (`kb_search`, migrate, Performix-over-SSH). See [`.cursor/mcp.json.example`](../.cursor/mcp.json.example). Do not confuse with `performix-bridge`.

GEPA text loop (hybrid reflection default):

```bash
curl -fsS -X POST http://127.0.0.1/arop/optimize -H 'Content-Type: application/json' -d '{"force":true}'
curl -fsS http://127.0.0.1/arop/gepa/pending
# approve + deploy → work/arop/gepa/<candidate_id>/
curl -fsS -X POST http://127.0.0.1/arop/gepa/approve -H 'Content-Type: application/json' \
  -d '{"candidate_id":"<id>"}'
curl -fsS -X POST http://127.0.0.1/arop/gepa/deploy -H 'Content-Type: application/json' \
  -d '{"candidate_id":"<id>"}'
```


### Using Prometheus + Grafana (obs host)

| Surface | URL | Notes |
|---------|-----|--------|
| API / Swagger | `http://<axion-ip>/docs` | Root `/` is 404 by design — use `/health`, `/ready`, `/metrics` |
| Prometheus | `http://<obs-ip>/prometheus/` | Graph is empty until you type a query |
| Grafana | `http://<obs-ip>/grafana/` | Login `admin` / `neuroswarm` |

**Prometheus (do this first):**

1. **Status → Targets** — `neuroswarm-gateway` should be **UP**
2. **Graph** → Expression → Execute:
   - `up`
   - `nexus_performix_ipc`
   - `nexus_performix_hotspot_pct`
   - `{__name__=~"nexus_.*"}`

Swagger API routes (KV, MAKS, tools, AROP) are **HTTP endpoints**, not Prometheus graphs. Metrics for dashboards come from `GET /metrics`.

Or end-to-end: `bash scripts/bootstrap-vm.sh` (requires `/ready` HTTP 200).

## Kubernetes one-command (Helm)

```bash
bash scripts/deploy-k8s.sh
# Windows:
# powershell -ExecutionPolicy Bypass -File scripts\deploy-k8s.ps1
```

Builds ARM64 gateway + llama images, optionally loads into kind, then:

`helm upgrade --install neuro ./helm/neuroswarm-arm`

Skip rebuilds: `SKIP_BUILD=1 SKIP_LLAMA_BUILD=1 bash scripts/deploy-k8s.sh`

## VM-first path

- `bootstrap-gcp.ps1` creates or verifies the GCP project prerequisites, restricted firewall rule, and Axion VM.
- `deploy-vm.ps1` runs the hardened end-to-end workflow from Windows: local validation, sync to `~/neuroswarm-arm`, remote validation, optional smoke-model setup, bootstrap, and evidence collection.
- `sync-vm.ps1` copies the repo to `~/neuroswarm-arm`. Use `-PreferGcloud` when Google Cloud CLI is available.
- `upload-models.ps1` uploads the three real GGUF files from `models/` to `/models` and creates the canonical aliases expected by Docker Compose.
- `validate-vm.sh` checks the Axion VM without changing it.
- `bootstrap-vm.sh` installs runtime packages (`docker.io` + `docker-compose-v2` on Ubuntu ARM), verifies models, starts Docker Compose with `--compatibility`, and captures evidence.
- `capture-evidence.sh` saves health/readiness/metrics/chat/tool-routing/log/benchmark artifacts under `benchmarks/results`.
- `prepare-models.sh` validates expected GGUF model files or creates demo symlinks from one small model.
- `deploy-k8s.sh` / `deploy-k8s.ps1` — ARM64 image build + Helm install.

## Safe defaults

Use a current public IP `/32` for demo firewall access. The scripts and Terraform examples intentionally avoid `0.0.0.0/0`.

For smoke testing, copy one small GGUF file to `/models` on the VM and run:

```bash
bash scripts/prepare-models.sh --demo-source /models/<small-demo-model>.gguf
```

For final real-model testing, upload the three licensed GGUF files and create aliases:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\upload-models.ps1
```
