# neuroswarm-arm

Helm chart for NeuroSwarm-Arm on ARM64 Kubernetes (gateway + three llama.cpp tiers + optional Prometheus/Grafana).

## Install

```bash
# Preferred on Axion: one-command from Windows
powershell -ExecutionPolicy Bypass -File scripts\sync-and-deploy.ps1 -Mode k8s

# Or on the VM after sync:
bash scripts/install-k3s-axion.sh
bash scripts/remote-helm-up.sh
```

Defaults for Axion + obs split: `observability.enabled=false` (use neuroswarm-obs Compose), `service.type=NodePort` (`30080`), hostPath `/models`, optional `okf.hostPath` / `work.hostPath`, gateway HPA enabled, **Qdrant** in-cluster (`qdrant.enabled=true`, `NSA_MEM_QDRANT_URL=http://qdrant:6333`).

```bash
# Build images (ARM64)
docker buildx build --platform linux/arm64 -f Dockerfile.arm64 -t neuroswarm-arm-gateway:dev --load .
docker buildx build --platform linux/arm64 -f docker/Dockerfile.llama-kleidiai -t nexus-arm/llama-kleidiai:server --load .

# One-command (local kind)
bash scripts/deploy-k8s.sh

# Or helm directly
helm upgrade --install neuro ./helm/neuroswarm-arm \
  --set image.gateway=neuroswarm-arm-gateway:dev \
  --set image.llama=nexus-arm/llama-kleidiai:server \
  --set models.hostPath=/models \
  --set observability.enabled=false
```

**k8s mode** stops Compose gateway/tiers/proxy on the same VM to free ports; obs VM is unchanged.

## Compose (non-K8s)

```bash
cp .env.example .env
docker compose --compatibility up --build -d
curl -fsS http://127.0.0.1:8000/health
```
