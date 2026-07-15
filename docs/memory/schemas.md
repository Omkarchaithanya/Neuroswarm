# Memory schemas & namespaces

## Core fields (`MemoryRecord`)

`uuid`, `namespace`, `owner`, `type`, `timestamp`, `importance`, `confidence`, `embedding`, `metadata`, `relationships`, `ttl_seconds`, `access_count`, `last_access`, `summary`, `content`, `version`, `source`, `tags`, `origin_agent`, `workflow_id`, `execution_id`, `reasoning_id`, `cost`, `latency`, `success_score`, `failure_reason`, `archived`, `provider_id`

## Types → default namespace

| MemoryType | Namespace |
|------------|-----------|
| USER | users/ |
| AGENT / FACT / EXPERIENCE | agents/ |
| TOOL | tools/ |
| WORKFLOW | workflows/ |
| EXECUTION / SUCCESS / FAILURE | execution/ |
| REASONING | reasoning/ |
| REFLECTION | reflection/ |
| PERFORMANCE | performance/ |
| BENCHMARK | benchmarks/ |
| COST | cost/ |
| LATENCY | latency/ |
| PROMPT | prompts/ |
| PLANNING | planner/ |
| SWARM | swarm/ |
| SYSTEM | system/ |
| EVOLUTION | evolution/ |
