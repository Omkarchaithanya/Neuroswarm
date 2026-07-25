"""Lean ~40-tool MCPGA-style router harness.

Uses the live ≥40-tool catalog under templates/mcp-servers when present.
Pads with synthetic distractors only if the catalog is still under 40.
Hash embeddings are used when NSA_ROUTER_MCPGA_HASH=1 or FastEmbed is unavailable
(CI-friendly). Prefer real FastEmbed for local/Axion measurement runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# CI default: hash. Set NSA_ROUTER_MCPGA_HASH=0 to force real backend attempt.
if os.getenv("NSA_ROUTER_MCPGA_HASH", "1") not in {"0", "false", "False"}:
    os.environ.setdefault("NSA_ROUTER_ALLOW_HASH", "1")
    os.environ.setdefault("NSA_ROUTER_EMBEDDING_BACKEND", "hash")
else:
    os.environ.setdefault("NSA_ROUTER_EMBEDDING_BACKEND", "fastembed")
    os.environ.pop("NSA_ROUTER_ALLOW_HASH", None)

from neuroswarm_arm.runtime.memory import build_memory_runtime
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.router import build_router, load_router_config
from neuroswarm_arm.runtime.router.models import ToolRecord
from neuroswarm_arm.runtime.router.tool_schema_builder import build_tool_schema, estimate_schema_tokens
from neuroswarm_arm.runtime.router.tool_serializer import serialize_tools_for_prompt

RESULTS = REPO_ROOT / "work" / "benchmarks" / "router_mcpga.json"
TOOLS = REPO_ROOT / "templates" / "mcp-servers"

# Queries keyed to live per-tool catalog namespaces.
SUITE = [
    {"query": "Search the web and summarize GitHub issues for the project", "expected": "github"},
    {"query": "Find a page in the browser and capture the visible text", "expected": "browser"},
    {"query": "Store structured data in postgres and query rows", "expected": "postgres"},
    {"query": "Use slack to send a channel update about the release", "expected": "slack"},
    {"query": "Upload an artifact to object storage", "expected": "s3"},
    {"query": "Search the public web for recent docs", "expected": "web"},
]


def _distractors(n: int) -> list[ToolRecord]:
    cats = [
        ("calendar", "Schedule meetings and calendar events"),
        ("email", "Send and read email messages"),
        ("jira", "Track Jira tickets and sprints"),
        ("notion", "Edit Notion pages and databases"),
        ("linear", "Manage Linear issues"),
        ("datadog", "Query Datadog metrics and monitors"),
        ("pagerduty", "Acknowledge PagerDuty incidents"),
        ("stripe", "List Stripe payments and customers"),
        ("twilio", "Send SMS via Twilio"),
        ("zoom", "Create Zoom meetings"),
        ("figma", "Export Figma design assets"),
        ("sentry", "Fetch Sentry error events"),
        ("redis", "Get and set Redis keys"),
        ("kafka", "Produce Kafka messages"),
        ("terraform", "Plan terraform infrastructure"),
        ("k8s", "List kubernetes pods and services"),
        ("docker", "Build and push docker images"),
        ("npm", "Publish npm packages"),
        ("pytest", "Run pytest suites"),
        ("linter", "Run static analysis linters"),
        ("translate", "Translate text between languages"),
        ("ocr", "Extract text from images via OCR"),
        ("pdf", "Parse PDF documents"),
        ("csv", "Load and transform CSV tables"),
        ("weather", "Fetch weather forecasts"),
        ("maps", "Geocode addresses on maps"),
        ("crypto", "Get cryptocurrency prices"),
        ("stocks", "Fetch equity stock quotes"),
        ("hris", "Look up employee HR records"),
        ("crm", "Update CRM contact records"),
        ("billing", "Generate customer invoices"),
        ("cdn", "Purge CDN cache entries"),
        ("dns", "Update DNS records"),
        ("vpn", "Manage VPN endpoints"),
    ]
    out: list[ToolRecord] = []
    for i in range(max(0, n)):
        name, desc = cats[i % len(cats)]
        tid = f"distract-{name}-{i}"
        out.append(
            ToolRecord(
                id=tid,
                name=tid,
                description=f"{desc} (synthetic distractor #{i})",
                params={"query": "string", "limit": "int"},
                tags=[name, "distractor"],
                example_prompts=[f"use {name} tool for task {i}"],
                output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            )
        )
    return out


def _hit(expected: str, tool_ids: list[str]) -> bool:
    exp = expected.lower()
    return any(exp in tid.lower() for tid in tool_ids)


def run_mcpga(*, top_k: int = 3) -> dict:
    scratch = REPO_ROOT / "work" / "benchmarks" / ".mcpga"
    scratch.mkdir(parents=True, exist_ok=True)
    cfg = load_router_config(REPO_ROOT)
    cfg.tool_metadata_root = TOOLS
    cfg.okf_root = scratch / "okf"
    cfg.okf_root.mkdir(exist_ok=True)
    cfg.index_path = scratch / "index"
    cfg.snapshot_dir = scratch / "snapshots"
    cfg.cache_dir = scratch / "cache"
    cfg.mem_store = scratch / "mem"
    cfg.enable_hot_reload = False
    cfg.ann_backend = "exact"
    cfg.top_k = top_k
    if os.getenv("NSA_ROUTER_MCPGA_HASH", "1") not in {"0", "false", "False"}:
        cfg.allow_hash = True
        cfg.embedding_backend = "hash"
    else:
        cfg.allow_hash = False
        cfg.embedding_backend = "fastembed"
    cfg.ensure_dirs()

    mem = build_memory_runtime(
        config=MemoryRuntimeConfig(store_root=scratch / "mem", provider="json", llm_mode="none")
    )
    router = build_router(cfg, start_sync=False, memory=mem)
    need = max(0, 40 - router.registry.size())
    for tool in _distractors(need):
        router.register_tool(tool)

    tool_count = router.registry.size()
    all_tools = router.registry.as_list()
    naive_tokens = sum(estimate_schema_tokens(build_tool_schema(t)) for t in all_tools)

    hits = 0
    reductions: list[float] = []
    rows: list[dict] = []
    for case in SUITE:
        result = router.route(str(case["query"]), top_k=top_k)
        ok = _hit(str(case["expected"]), result.tool_ids)
        hits += int(ok)
        selected = [t for t in all_tools if t.id in set(result.tool_ids)]
        sel_tokens = sum(estimate_schema_tokens(build_tool_schema(t)) for t in selected)
        reduction = 1.0 - (sel_tokens / max(1, naive_tokens))
        reductions.append(reduction)
        rows.append(
            {
                "query": case["query"],
                "expected": case["expected"],
                "tool_ids": result.tool_ids,
                "hit": ok,
                "confidence": result.confidence_top1,
                "high_confidence": result.high_confidence,
                "token_reduction": reduction,
                "prompt_chars": len(serialize_tools_for_prompt(result.tools)),
            }
        )

    payload = {
        "tool_count": tool_count,
        "embedding_backend": router.embedder.backend_name,
        "top_k": top_k,
        "top3_hit_rate": hits / max(1, len(SUITE)),
        "avg_token_reduction_ratio": sum(reductions) / max(1, len(reductions)),
        "note": (
            "Internal harness (not a public MCPGA paper). "
            "Use NSA_ROUTER_MCPGA_HASH=0 for FastEmbed measurement."
        ),
        "cases": rows,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    router.shutdown()
    print(json.dumps({k: payload[k] for k in payload if k != "cases"}, indent=2))
    return payload


if __name__ == "__main__":
    run_mcpga()
