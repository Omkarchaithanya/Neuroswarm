# Trace Flow

## Mandatory spine

```
nexus.armora.request
  └─ nexus.armora.admission
       └─ nexus.armora.policy
            └─ nexus.armora.budget
  └─ nexus.haoe.workflow
       └─ nexus.dipa.infer
            ├─ nexus.dipa.planner
            ├─ nexus.dipa.routing
            ├─ nexus.aqr.quant (connector)
            ├─ nexus.awpp.warm (connector)
            ├─ nexus.maks.kv (connector)
            ├─ nexus.dipa.backend
            └─ nexus.dipa.streaming
  └─ nexus.armora.rcis
  └─ nexus.rof.export
```

## Sequence

```mermaid
sequenceDiagram
  participant Client
  participant GW as Gateway
  participant ROF
  participant Budget
  participant HAOE
  participant DIPA
  participant RCIS

  Client->>GW: POST /v1/chat/completions
  GW->>ROF: start_request
  GW->>ROF: admission/policy/budget spans
  GW->>Budget: create_and_freeze
  GW->>HAOE: submit_workflow
  HAOE->>ROF: haoe.workflow span
  HAOE->>DIPA: infer
  DIPA->>ROF: planner/routing/infer spans
  DIPA-->>GW: response
  GW->>RCIS: finalize cost
  GW->>ROF: rcis span + CostReportGenerated
  ROF-->>Client: async export
```

## Context propagation

- `RuntimeTraceContext` in `contextvars` (AsyncIO-safe)
- Carrier: `inject()` / `extract()` for worker pools + streaming
- HAOE: `CorrelationIds` ↔ `RuntimeTraceContext.from_haoe_correlation`
- Baggage keys: `nexus.request_id`, `nexus.envelope_id`, …
