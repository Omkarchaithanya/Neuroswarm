# Performix integration

Telemetry bridge from KV load/save hot path to arm-mcp PMU recipes.

## Env

| Var | Default | Meaning |
|-----|---------|---------|
| `NSA_PERFORMIX_SAMPLE` | `0` | `1` = async PMU sample after KV load/save |
| `NSA_AROP_PERFORMIX_MCP` | `` | HTTP MCP URL (`http://performix-bridge:8090`) |
| `NSA_PERFORMIX_PMU_RECIPE` | `cpu_microarchitecture` | apx recipe name |
| `NSA_PERFORMIX_TIMEOUT_S` | `30` | MCP call timeout |

## Span attributes

| Attribute | Type | Source |
|-----------|------|--------|
| `gen_ai.arm.l3_miss_rate` | float | Performix recipe / parser |
| `gen_ai.arm.sve_util_pct` | float | Performix recipe / parser |
| `gen_ai.arm.branch_mispredict_pct` | float | Performix recipe / parser |
| `gen_ai.arm.performix_op` | string | `kv_load` or `kv_save` |
| `gen_ai.arm.performix_skipped` | bool | Set when arm-mcp unreachable |

## Behavior

- Bridge calls `list_tools()` on first use and introspects `apx_recipe_run` schema.
- Sampling runs in a daemon thread (`schedule_sample`) — hot path adds <5ms.
- Fail-soft: unreachable MCP logs warning, inference continues.

## Distinction

- `neuroswarm_arm/telemetry/performix_bridge.py` — KV hot-path PMU attrs.
- `neuroswarm_arm/evolution/performix_bridge.py` — HTTP JSON-RPC service for AROP.
