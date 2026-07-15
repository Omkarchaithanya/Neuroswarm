# GCP Ops Agent Notes

The local Docker Compose stack exposes application metrics through Prometheus and Grafana.
For VM-level CPU, memory, disk, and network metrics on C4A Arm, install the Google Cloud Ops Agent on Ubuntu 24.04 ARM64.

Use this only after the demo stack works:

```bash
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install
sudo systemctl status google-cloud-ops-agent --no-pager
```

The VM service account must have permissions for Cloud Monitoring and Cloud Logging. Keep cloud-level observability separate from the app-level Prometheus metrics used for benchmark evidence.
