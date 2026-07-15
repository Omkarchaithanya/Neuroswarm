<<<<<<< HEAD
# Setup

Use `docs/gcp-axion-setup.md` for the recommended hackathon deployment.

Install Python dependencies with [uv](https://docs.astral.sh/uv/) from the repo root:

```bash
uv sync --all-groups
```

The MVP is intentionally Docker Compose first:

```bash
cp .env.example .env   # bootstrap-vm.sh does this on Axion with cp -n
docker compose up --build -d
curl http://127.0.0.1:8000/health
```

Move to Helm/GKE only after the single-VM Axion demo is working and benchmarked.
=======
﻿# Setup

This project is designed to run on Arm64 VMs like OCI Ampere A1, Azure Arm, or GCP Axion.

Run the generator from the workspace root:

```powershell
.\setup-neuroswarm-arm.ps1
```
>>>>>>> 8d3d8a66b9c2ddab68c72e55592421d807031c84
