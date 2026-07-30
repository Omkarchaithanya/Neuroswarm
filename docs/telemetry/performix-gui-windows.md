# Arm Performix GUI on Windows → Axion llama.cpp

Interactive desktop workflow for this NeuroSwarm stack. Automation still uses host `apx` on Axion; the GUI is for visual exploration of the same recipes.

Installer (already downloaded / installed on this machine):

- Download: `%USERPROFILE%\Downloads\ArmPerformix-windows-x64.exe`
- Install dir: `%LOCALAPPDATA%\Programs\Arm Performix`
- Start Menu: **Arm Performix**

Official guide: [learn.arm.com/install-guides/performix](https://learn.arm.com/install-guides/performix/)

## Targets → SSH to neuroswarm-axion

Direct SSH from this network is open (preferred):

| Field | Value |
|-------|--------|
| Host | `104.198.180.95` |
| Port | `22` |
| User | `tejaswini2482_gmail_com` |
| Auth | Private key → `%USERPROFILE%\.ssh\google_compute_engine` |

Steps in the app:

1. Open **Arm Performix**
2. **Targets** → Add / New target
3. Fill the table above → **Test connection**
4. On first use: **Install tools** / deploy agents to the target
5. Confirm target shows Ready

If public `:22` is later blocked by GCP firewall, use IAP instead:

```powershell
gcloud compute start-iap-tunnel neuroswarm-axion 22 `
  --local-host-port=localhost:2222 `
  --zone=us-central1-a `
  --project=project-5bcdea88-8805-4908-991
```

Then Host=`127.0.0.1`, Port=`2222`, same user/key.

## Run Code Hotspots against live llama.cpp

1. Select recipe **Code Hotspots** (`code_hotspots`)
2. Target = Axion SSH target
3. Workload = **Attach to existing process**
4. Pick the host-visible `llama-server` for **tier3** (DeepSeek 7B / Kleidi), e.g. from Axion:

```bash
pgrep -af llama-server
# Prefer the line with DeepSeek / 7B / longest uptime under load
```

5. Duration ~15–40s
6. Before/while capturing, generate chat load against the gateway (Axion `:80` or tunnel)
7. **Run Recipe** → inspect hotspots / IPC in the GUI

Optional second recipe: **Instruction Mix** on the same PID under load.

## CLI parallel (agent / CI — same honesty rules)

On Axion:

```bash
cd ~/neuroswarm-arm
PID=$(pgrep -af 'DeepSeek|llama-server.*7B' | awk '{print $1}' | head -1)
# fallback: busiest llama-server
NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 \
  PERFORMIX_PID=$PID \
  bash scripts/refresh-performix-snapshot.sh
```

Expect `work/performix/snapshot.json` with `"source": "apx"` (never silent demo). On failure with `ALLOW_DEMO=0`, the script writes `source=unavailable` (does **not** leave a stale snapshot). Grafana **Performix** panels read Prometheus gauges from the gateway collector — demo/unavailable snapshots export `nexus_performix_available=0` (zeros), never fake IPC.

### Long-lived refresh (cron / systemd)

Keep gauges honest under load by refreshing every few minutes (not one-shot only):

```bash
# crontab -e on Axion (example: every 2 minutes)
*/2 * * * * cd /home/tejaswini2482_gmail_com/neuroswarm-arm && \
  NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 \
  bash scripts/refresh-performix-snapshot.sh >>work/performix/cron.log 2>&1
```

Confirm Axion `.env` has `NSA_PERFORMIX_ALLOW_DEMO=0`.

## Grafana on Windows (obs host — not Axion `:3000`)

Prometheus + Grafana run on **`neuroswarm-obs`**, not on Axion. Tunnel Grafana to your laptop:

```powershell
# Grafana on obs (not Axion)
ssh -L 13000:127.0.0.1:3000 tejaswini2482_gmail_com@<obs-ip-or-iap>
# → http://127.0.0.1:13000/grafana/  (Performix dashboard)
```

IAP example if public SSH is blocked:

```powershell
gcloud compute start-iap-tunnel neuroswarm-obs 22 `
  --local-host-port=localhost:2223 `
  --zone=us-central1-a `
  --project=project-5bcdea88-8805-4908-991

ssh -i $env:USERPROFILE\.ssh\google_compute_engine `
  -L 13000:127.0.0.1:3000 `
  -p 2223 tejaswini2482_gmail_com@127.0.0.1
```

Open `http://127.0.0.1:13000/grafana/` → Performix / RMF dashboards. Panels are Prometheus-backed (`nexus_performix_*` from job `neuroswarm-gateway`). When the VM snapshot is dead you should see **0 / unavailable**, never silent dummy values.

## Honesty

- Attach to a **live** `llama-server` PID under chat load
- Do **not** use system-wide idle capture unless `PERFORMIX_ALLOW_SYSTEM_WIDE=1`
- Prefer a single stack (Compose **or** k3s), not both
- Never treat `source=demo|synthetic|unavailable` as live in Grafana
