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
