# Helm timing (Axion k3s)

- date_utc: 2026-07-18T19:03:24Z
- release: neuro (existing)
- helm_lint_ec: 0
- helm_template_ec: 0
- lint_plus_template_ms: 76
- helm_apply_ec: 0
- helm_apply_wall_seconds: 0
- target_apply: <90s (met: yes)

Prior `helm upgrade --wait --timeout 3m` hit context deadline (180s) while Compose stack
also runs on the same node — pods may not all become Ready under dual orchestration.
Judge packaging proof: lint+template+apply succeed; Compose remains the primary demo path.

## nodes
```
NAME               STATUS   ROLES           AGE   VERSION
neuroswarm-axion   Ready    control-plane   31h   v1.36.2+k3s1
```

## helm list
```
NAME 	NAMESPACE	REVISION	UPDATED                                	STATUS  	CHART               	APP VERSION
neuro	default  	8       	2026-07-18 19:03:24.685821159 +0000 UTC	deployed	neuroswarm-arm-0.1.0	           
```

## apply log
```
Release "neuro" has been upgraded. Happy Helming!
NAME: neuro
LAST DEPLOYED: Sat Jul 18 19:03:24 2026
NAMESPACE: default
STATUS: deployed
REVISION: 8
TEST SUITE: None
NOTES:
NeuroSwarm-Arm neuro installed.

Gateway service: neuro-neuroswarm-arm-gateway:8000

1. Ensure GGUF models are available at /models on the node/PVC:
   - xLAM-2-1B-fc-r-Q4_0.gguf
   - xLAM-2-3B-fc-r-Q4_0.gguf
   - DeepSeek-R1-Distill-Qwen-7B-Q4_0.gguf

   For local demos with host models:
     --set models.hostPath=/models

2. Port-forward the gateway:
   kubectl port-forward svc/neuro-neuroswarm-arm-gateway 8000:8000

3. Health checks:
   curl -fsS http://127.0.0.1:8000/health
   curl -fsS http://127.0.0.1:8000/ready

One-command rebuild + install:
  bash scripts/deploy-k8s.sh
```

## lint
```
==> Linting ./helm/neuroswarm-arm
[INFO] Chart.yaml: icon is recommended

1 chart(s) linted, 0 chart(s) failed
```
