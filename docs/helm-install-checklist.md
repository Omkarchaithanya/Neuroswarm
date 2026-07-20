# Helm install checklist (real cluster, not lint-only)

CI already runs `helm lint` + `helm template`. Judges care about a **real install**.

## Target

- Chart: `helm/neuroswarm-arm`
- Image: `image.llama=nexus-arm/llama-kleidiai:server`
- Cold apply time goal: **&lt;90s** (chart apply; image pulls may dominate separately)

## Steps

```bash
# On GKE Arm node pool / k3s aarch64 / EKS Graviton
export NS=neuroswarm
kubectl create ns "$NS" || true

# Time chart apply only
/usr/bin/time -f 'helm_elapsed_sec=%e' \
  helm upgrade --install neuroswarm ./helm/neuroswarm-arm \
    -n "$NS" \
    --set image.llama=nexus-arm/llama-kleidiai:server \
    --wait --timeout 10m

kubectl -n "$NS" get pods,svc
kubectl -n "$NS" port-forward svc/neuroswarm-gateway 8000:8000
curl -fsS http://127.0.0.1:8000/health
```

Or: `bash scripts/deploy-k8s.sh`

## Record

Write elapsed seconds + `kubectl get pods` into `docs/evidence/latest/helm-install.txt` after a successful run.

## Compose-first

If no cluster yet, Compose on Axion is the MVP (`docs/setup.md`). Helm is P1 polish, not a P0 blocker for Cloud AI submit.
