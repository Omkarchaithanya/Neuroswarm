# Tool Search & Router Pillar-Wiring Contract

> **Status:** Draft — companion to `CURSOR_PROMPT_tool_search.md`. Cursor Agent should treat this as the binding spec. If a proposed implementation conflicts with this file, this file wins; flag the conflict in the PR description rather than silently diverging.

> **Repo baseline:** `https://github.com/Omkarchaithanya/Neuroswarm` @ `main` (commit `9401924`, Jul 31 2026).

---

## 1. Scope and non-goals

**In scope**

1. A real, spec-compliant Hermes `tool_search` subsystem (bridge tool, listing manifest, auto/on/off mode, threshold-pct activation, default/max limits, listing budget).
2. Hooking the existing `SemanticToolRouter` (`neuroswarm_arm/runtime/router/`) into every pillar and layer claimed in the project spec, end to end, with test coverage.
3. A `RouterResult` envelope that travels from the router to every downstream caller (`ReasoningGovernor.cap`, `CascadeRouter._handle_*`, DIPA `DecisionEngine`, MAKS slot affinity, AWPP warmer), so the router's confidence/score/token-reduction is never thrown away.

**Out of scope (do NOT change)**

- The semantic search algorithm itself (embedder, ANN, hybrid, reranker). This contract only adds a new **mode of presenting the catalog**, not a new search algorithm.
- `NSA_ROUTER_*` config keys and their semantics.
- Pillar 1 ASCR, Pillar 3 CXL backend, Pillar 4 RTG, L2 DIPA, L4 Mem0, L5 MAKS — implementations stay as-is. We are only **wiring** the router into them.
- The 4xx bridge that would touch the actual `llama.cpp` tool-call parser. Bridge tool response is consumed by the same DIPA request loop that already handles regular tool calls.

**Honesty constraints**

- ARM MTE is **unavailable on GCP Axion** (per `neuroswarm_arm/runtime/maks/backends/future_mte_backend.py:21`). The MAKS `MTEBackend.AVAILABLE` is `False` on this hardware. Any "MTE-secured" claim must check `AVAILABLE` at runtime and fall back to the `ram`/`mmap` backend with a logged warning. Do **not** assert MTE tags in CI; gate the test on a feature flag.
- CXL is also a future stub on Axion (`FutureCXLBackend`). Same rule: capability check, no hard dependency.

---

## 2. Hermes `tool_search` spec (binding)

Reference: `https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-search`

### 2.1 YAML config block (paste verbatim into `.env.example` and a new `ToolSearchConfig.from_env`)

```yaml
# Hermes tool_search — deferrable tool discovery bridge.
# https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-search
tools:
  tool_search:
    enabled: auto          # auto (default) | on | off
    threshold_pct: 10       # 0-100; auto mode activates above this fraction of context window
    search_default_limit: 5
    max_search_limit: 20
    listing: auto           # auto (default) | on | off — embed grouped name+description manifest
    listing_max_tokens: 20000
```

**Defaults are non-negotiable.** `enabled: auto`, `threshold_pct: 10`, `search_default_limit: 5`, `max_search_limit: 20`, `listing: auto`, `listing_max_tokens: 20000`. The previous draft that used `threshold_pct: 5` is wrong and must not be re-introduced.

### 2.2 Activation rule

Given a request with `context_length = C` tokens of usable window:

```
deferred_tokens = sum(estimate_schema_tokens(tool.schema) for tool in registry if not in_initial_set)
share            = deferred_tokens / C
mode             = "pass_through" if enabled == "off"
                 | "bridge"       if enabled == "on" and any(deferrable)
                 | "bridge"       if enabled == "auto" and share >= threshold_pct/100
                 | "pass_through" otherwise
```

- `pass_through`: ship the regular top-K schemas (current behavior, untouched).
- `bridge`: ship **zero deferrable tool schemas**. Instead, ship one synthetic tool `tool_search` whose schema is fixed, and a **listing manifest** describing every deferrable tool by name + one-line description (truncated to fit `listing_max_tokens`).

### 2.3 Bridge tool contract

A single synthetic tool, always named `tool_search`, with this exact JSON-schema:

```json
{
  "type": "function",
  "function": {
    "name": "tool_search",
    "description": "Search the deferred tool catalog by free-text query. Returns name+description listings grouped by server. Use this when the user's request may match a tool you don't see in the active tools list.",
    "parameters": {
      "type": "object",
      "properties": {
        "query":  {"type": "string",  "description": "Free-text tool/feature query"},
        "limit":  {"type": "integer", "minimum": 1, "maximum": 20, "default": 5, "description": "Max results; capped at max_search_limit."},
        "scope":  {"type": "string",  "enum": ["all", "server"], "default": "all"}
      },
      "required": ["query"],
      "additionalProperties": false
    }
  }
}
```

**Bridge tool response shape** (returned to the model as the tool result):

```json
{
  "mode": "tool_search",
  "query": "<echoed query>",
  "limit": 5,
  "results": [
    {"id": "aws.s3.presign_url", "name": "s3_presign_url", "description": "Generate a presigned S3 URL for upload/download.", "server": "aws-mcp"},
    ...
  ],
  "truncated": false
}
```

The model then issues a **second** regular tool call for the chosen tool name, which DIPA already knows how to handle. No new parser.

### 2.4 Listing manifest format (embedded when `listing: auto` and bridge mode)

A single system-prompt block, capped at `listing_max_tokens`, structured as:

```
<tool_listing>
server: aws-mcp
  - s3_presign_url — Generate a presigned S3 URL for upload/download.
  - s3_list_buckets — List S3 buckets in the configured account.
server: github-mcp
  - gh_create_issue — Create a GitHub issue in a repo.
  ...
</tool_listing>
```

Truncation policy: drop from the end. When truncated, append a footer line: `... and N more tools; call tool_search(query="...") to drill in.`

Token count: estimate with the existing `estimate_schema_tokens` (already in `neuroswarm_arm/runtime/router/tool_schema_builder.py`). Treat the manifest as a single virtual schema for budgeting.

### 2.5 Forbidden behaviors

- Do **not** ship full tool schemas in bridge mode — only the manifest.
- Do **not** call `tool_search` on the model's behalf (e.g. eager expansion) unless `enabled == "on"`.
- Do **not** raise the listing budget silently. If truncation happens, set `truncated=true` in metrics and emit a router event.
- Do **not** parse or rewrite the model's tool-call JSON. The bridge tool is consumed by the existing DIPA tool-execution loop.

---

## 3. Router-to-pillar wiring matrix (binding)

Each row is a contract that Cursor must satisfy with **code + a test**. `?` = capability-gated, may no-op on Axion.

| From (router artifact) | To (pillar / layer) | Wiring point | Required test |
|---|---|---|---|
| `RoutingResult.tools` (top-K) | **L2 DIPA** cascade | Already done in `runtime/dipa/router/decision_engine.py` via `CostRouter`. Keep, but feed `routing_result` into `plan.metadata["router"]`. | `tests/runtime/router/test_router_cascade_wiring.py` already covers it; extend with metadata assertion. |
| `RoutingResult.confidence_top1` | **Pillar 4 RTG** (`ReasoningGovernor.cap`) | Add `router_result: RoutingResult | None = None` kwarg to `ReasoningGovernor.cap`. When provided, **before** computing the cap, set `plan.tool_confidence_top1 = router_result.confidence_top1` (only if it's higher than the existing value, so upstream signals still win). | `tests/runtime/governor/test_governor_router_wiring.py` |
| `RoutingResult` | **HAOE chat** flow | `semantic_route` step in `runtime/haoe/integration/chat.py` already populates `state["cost_router"]`; **also** stash the full `RoutingResult` in `ctx.baggage["router_result"]` so downstream handlers can read it. | `tests/runtime/haoe/test_chat_router_wiring.py` |
| `RoutingResult.tools` (top-K) | **`CascadeRouter._handle_via_dipa` / `_handle_legacy`** | Pass `router_result` extracted from kwargs into `self.governor.cap(plan, router_result=router_result)`. Backward-compatible: when `router_result is None`, behavior is identical to today. | `tests/runtime/dipa/test_cascade_router_integration.py` |
| `RoutingResult.tool_ids` | **L5 MAKS slot affinity** (`okf_slot_affinity.py`) | Add optional `tool_ids: tuple[str, ...] = ()` kwarg to `BlockHashSlotAffinity.hash_block`, `get_slot`, `assign_slot`. When non-empty, the block hash is mixed with the sorted tool_ids before hashing, so each tool's KV block maps to its own slot namespace. **Backwards compatible** — the default tuple produces the same hash as the old `content`-only path (assert in test). | `tests/runtime/dipa/cache/test_okf_slot_affinity.py` (extend existing) |
| `RoutingResult.tools` | **L4 Mem0 / OKF** fact context | In `build_chat_handlers.mem0_recall`, add a call to `router.augment_query(query, tools=result.tools)` that returns a query string biased toward the routed tools' domains — Mem0 recall stays where it is; the new code is a query-side bias, not a write. | `tests/runtime/memory/test_mem0_router_bias.py` |
| `RoutingResult.tools` (top-K) | **AWPP predictive warmer** | In `runtime/awpp/warmers/tool.py`, when a `RoutingResult` is present, call `markov.record_tools([t.id for t in result.tools])` to pre-warm their backend clients. | `tests/runtime/awpp/test_router_warmer.py` |
| `RoutingResult` | **Hermes `tool_search` bridge** | `build_chat_handlers` adds a new step `tool_search_activation(state, ctx)` that computes deferred-token share, decides pass_through vs bridge, and (in bridge mode) mutates `state["tool_schemas"]` to be `[bridge_tool_schema]` and `state["tool_prompt_block"]` to be the listing manifest. | `tests/runtime/haoe/test_tool_search_activation.py` |

The "?" caveat applies to MAKS-MTE only: when `MTEBackend.AVAILABLE is False`, the `okf_slot_affinity.tool_ids` path must still work (it doesn't require MTE), but the test should not assert MTE tag generation — assert that `tool_ids` produces a *deterministic, distinct* hash and that the slot lookup is correct.

---

## 4. New module: `neuroswarm_arm/runtime/router/tool_search/`

```
neuroswarm_arm/runtime/router/tool_search/
├── __init__.py
├── config.py            # ToolSearchConfig dataclass + from_env()
├── activation.py        # decide_mode(deferred_tokens, ctx_length, cfg) -> "pass_through"|"bridge"
├── bridge_tool.py       # BRIDGE_TOOL_SCHEMA constant
├── listing.py           # build_listing_manifest(registry, max_tokens) -> str
├── response.py          # build_bridge_response(query, results, limit) -> dict
└── metrics.py           # tool_search_mode_total{bridge,pass_through}, tool_search_truncated_total
```

### 4.1 `ToolSearchConfig`

```python
@dataclass(slots=True, frozen=True)
class ToolSearchConfig:
    enabled: Literal["auto", "on", "off"] = "auto"
    threshold_pct: float = 10.0
    search_default_limit: int = 5
    max_search_limit: int = 20
    listing: Literal["auto", "on", "off"] = "auto"
    listing_max_tokens: int = 20000

    @classmethod
    def from_env(cls) -> "ToolSearchConfig": ...
```

Env mapping (one prefix, no nested keys; flat is easier to ship and to override in compose):

```
TOOL_SEARCH_ENABLED=auto|on|off
TOOL_SEARCH_THRESHOLD_PCT=10
TOOL_SEARCH_DEFAULT_LIMIT=5
TOOL_SEARCH_MAX_LIMIT=20
TOOL_SEARCH_LISTING=auto|on|off
TOOL_SEARCH_LISTING_MAX_TOKENS=20000
```

A single comment block in `.env.example` explaining the mapping and the one-time YAML-equivalent example is sufficient. Do not invent a YAML parser.

### 4.2 `decide_mode`

Pure function, no I/O. Signature:

```python
def decide_mode(
    *,
    enabled: str,
    threshold_pct: float,
    context_length: int,
    deferred_schema_tokens: int,
    has_deferrable: bool,
) -> Literal["pass_through", "bridge"]:
    ...
```

### 4.3 `build_listing_manifest`

Inputs: `ToolRegistry`, `max_tokens`. Output: manifest string. Truncation: drop from the end, append `... and N more tools; call tool_search(...)` footer. Token estimation: re-use `estimate_schema_tokens` treating the manifest as a single schema.

### 4.4 `build_bridge_response`

Pure function from `(query: str, results: list[ToolRecord], limit: int)` to the dict shape in §2.3. Cap `results` to `limit`. Set `truncated=True` if the input was longer than `limit`.

---

## 5. Touch list (files to create or modify)

**Create**

- `neuroswarm_arm/runtime/router/tool_search/__init__.py`
- `neuroswarm_arm/runtime/router/tool_search/config.py`
- `neuroswarm_arm/runtime/router/tool_search/activation.py`
- `neuroswarm_arm/runtime/router/tool_search/bridge_tool.py`
- `neuroswarm_arm/runtime/router/tool_search/listing.py`
- `neuroswarm_arm/runtime/router/tool_search/response.py`
- `neuroswarm_arm/runtime/router/tool_search/metrics.py`
- `tests/runtime/router/test_bridge_tools.py`
- `tests/runtime/router/test_tool_search_activation.py`
- `tests/runtime/router/test_listing_manifest.py`
- `tests/runtime/dipa/test_cascade_router_integration.py`
- `tests/runtime/governor/test_governor_router_wiring.py`
- `tests/runtime/haoe/test_chat_router_wiring.py`
- `tests/runtime/haoe/test_tool_search_activation.py`
- `tests/runtime/memory/test_mem0_router_bias.py`
- `tests/runtime/awpp/test_router_warmer.py`

**Modify**

- `.env.example` — append the `TOOL_SEARCH_*` block with a YAML-equivalent comment.
- `neuroswarm_arm/runtime/router/__init__.py` — re-export `ToolSearchConfig` and `decide_mode`.
- `neuroswarm_arm/runtime/router/orchestration.py` — `build_routed_inference_hints` now also accepts `tool_search_cfg: ToolSearchConfig | None` and (in bridge mode) replaces `tool_schemas` with the bridge schema and `tool_prompt_block` with the manifest.
- `neuroswarm_arm/runtime/router/cost_router.py` — no semantic change. Just ensure the decision dict now includes `tool_search_mode`.
- `neuroswarm_arm/governor.py` — `cap(plan, router_result=None)`. When `router_result` is not None, patch `plan.tool_confidence_top1 = max(plan.tool_confidence_top1, router_result.confidence_top1)` before delegating to RTG/legacy.
- `neuroswarm_arm/inference/cascade.py` — both `_handle_via_dipa` and `_handle_legacy` extract `router_result` from `**kwargs` and pass it to `self.governor.cap(plan, router_result=router_result)`.
- `neuroswarm_arm/runtime/dipa/cache/okf_slot_affinity.py` — add `tool_ids: tuple[str, ...] = ()` to `hash_block`, `get_slot`, `assign_slot`. Backwards-compatible default: empty tuple, hash identical to old.
- `neuroswarm_arm/runtime/dipa/interfaces/types.py` — add `router_result: RoutingResult | None = None` to `InferenceRequest.baggage`-friendly path (or a dedicated field; do **not** add a circular import).
- `neuroswarm_arm/runtime/haoe/integration/chat.py` — `semantic_route` step stashes full `RoutingResult` in `ctx.baggage["router_result"]`. New step `tool_search_activation` runs after `semantic_route` and before `cascade_infer`. Mem0 recall uses `router.augment_query(...)` query bias when available.
- `neuroswarm_arm/runtime/awpp/warmers/tool.py` — accept optional `router_result`, call `markov.record_tools([t.id for t in router_result.tools])` when present.
- `neuroswarm_arm/runtime/router/router_metrics.py` — register two new gauges: `tool_search_mode_total{bridge,pass_through}`, `tool_search_truncated_total`.

---

## 6. Acceptance criteria (Cursor must self-check before declaring done)

1. `grep -rn "tool_search" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.toml" --include="*.md" .` returns matches in:
   - the new `tool_search/` package
   - the new test files
   - `neuroswarm_arm/runtime/haoe/integration/chat.py`
   - `neuroswarm_arm/runtime/router/orchestration.py`
   - `.env.example`
2. `grep -rn "TOOL_SEARCH_" .env.example` returns 6 lines (one per key).
3. `pytest tests/runtime/router/test_bridge_tools.py tests/runtime/router/test_tool_search_activation.py tests/runtime/router/test_listing_manifest.py -q` passes; the test files actually exist on disk.
4. `pytest tests/runtime/dipa/test_cascade_router_integration.py tests/runtime/governor/test_governor_router_wiring.py tests/runtime/haoe/test_chat_router_wiring.py tests/runtime/haoe/test_tool_search_activation.py tests/runtime/memory/test_mem0_router_bias.py tests/runtime/awpp/test_router_warmer.py -q` passes.
5. `pytest tests/runtime/router/ tests/runtime/dipa/cache/test_okf_slot_affinity.py -q` — existing tests still pass (no regression).
6. In bridge mode, the request's `tool_schemas` field is exactly `[BRIDGE_TOOL_SCHEMA]` (one element) and **does not** contain any of the deferrable tools' full schemas.
7. In bridge mode, the system prompt includes a `<tool_listing>...</tool_listing>` block whose estimated token count is `≤ listing_max_tokens`.
8. With `enabled=off`, behavior is byte-identical to today's `SemanticToolRouter` flow for any request — assert in a test using a snapshot of `state["tool_schemas"]` and `state["tool_prompt_block"]`.
9. `MTEBackend.AVAILABLE` is honored: no test asserts MTE tag generation on a non-MTE host. Use `pytest.mark.skipif(not MTEBackend.AVAILABLE, reason="MTE not exposed on this host")`.
10. `git diff --stat` shows the file list above (creates + modifies) and net delta ≤ +800/-100 lines; PR description includes the contract reference and the test list.

---

## 7. Open questions for the human reviewer (do not block the prompt)

- The `MemoryCompressionConfig` block (L4 "90% token reduction") is a marketing claim, not a spec. The prompt does **not** require a measured 90% number — only that the existing `Mem0` + `OKF` flow is invoked with a router-biased query (see wiring matrix row L4).
- The MAKS "2x concurrent agents" and "40-70% dedup" are also marketing claims. The prompt requires the **capability** (tool_ids-aware slot affinity) to be in place; the actual dedup ratio is measured by `benchmarks/maks_multi_agent_dedup_bench.py`, which already exists and is out of scope for this PR.

---

## 8. Glossary

- **Bridge mode**: the request is shipped with `tool_search` as the only tool, plus a listing manifest. The model calls `tool_search` to discover, then a second regular call to actually invoke.
- **Pass-through mode**: today's behavior — the router picks top-K, those schemas go in the prompt.
- **Deferrable tool**: a tool that is registered in `ToolRegistry` but **not** part of the initial top-K selection for the current query.
- **Listing manifest**: a name+description-only rendering of the deferred catalog, used to give the model awareness without paying the schema-token cost.
