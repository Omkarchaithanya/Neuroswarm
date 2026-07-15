# Runtime Metrics Framework (RMF)

RMF is the NEXUS-ARM **metrics operating system**.

- Every runtime subsystem **publishes** metrics into RMF.
- RMF **owns** definitions, labels, aggregation, and scrape text.
- Prometheus / OpenMetrics / OTLP are **exporters only**.

Package: `neuroswarm_arm/metrics/`

| Doc | Purpose |
|-----|---------|
| [architecture.md](architecture.md) | Integration with ARMORA, HAOE, DIPA, ROF, AROP, … |
| [catalogue.md](catalogue.md) | Full metric catalogue by domain |
| [naming.md](naming.md) | Naming + label strategy |
| [promql.md](promql.md) | PromQL examples |
| [grafana.md](grafana.md) | Dashboard guide |
| [alerting.md](alerting.md) | Alert rules |
| [developer.md](developer.md) | How to publish metrics from a plane |
| [plugin-guide.md](plugin-guide.md) | Extending RMF without editing ARMORA |

Env prefix: `NSA_RMF_*`
