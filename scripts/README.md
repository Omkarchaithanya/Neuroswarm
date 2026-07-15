# Deployment Scripts

## VM-first path

- `bootstrap-gcp.ps1` creates or verifies the GCP project prerequisites, restricted firewall rule, and Axion VM.
- `deploy-vm.ps1` runs the hardened end-to-end workflow from Windows: local validation, sync to `~/neuroswarm-arm`, remote validation, optional smoke-model setup, bootstrap, and evidence collection.
- `sync-vm.ps1` copies the repo to `~/neuroswarm-arm`. Use `-PreferGcloud` when Google Cloud CLI is available.
- `upload-models.ps1` uploads the three real GGUF files from `models/` to `/models` and creates the canonical aliases expected by Docker Compose.
- `validate-vm.sh` checks the Axion VM without changing it.
- `bootstrap-vm.sh` installs runtime packages (`docker.io` + `docker-compose-v2` on Ubuntu ARM), verifies models, starts Docker Compose with `--compatibility`, and captures evidence.
- `capture-evidence.sh` saves health/readiness/metrics/chat/tool-routing/log/benchmark artifacts under `benchmarks/results`.
- `prepare-models.sh` validates expected GGUF model files or creates demo symlinks from one small model.

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
