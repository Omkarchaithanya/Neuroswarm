"""Lean ~40-tool MCPGA-style router harness (6 real templates + distractors).

Writes work/benchmarks/router_mcpga.json with top-3 accuracy and token_reduction_ratio.
Uses NSA_ROUTER_ALLOW_HASH=1 so CI does not require HF downloads.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("NSA_ROUTER_ALLOW_HASH", "1")

from neuroswarm_arm.runtime.memory import build_memory_runtime
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.router import build_router, load_router_config
from neuroswarm_arm.runtime.router.models import ToolRecord
from neuroswarm_arm.runtime.router.tool_schema_builder import build_tool_schema, estimate_schema_tokens
from neuroswarm_arm.runtime.router.tool_serializer import serialize_tools_for_prompt

RESULTS = REPO_ROOT / "work" / "benchmarks" / "router_mcpga.json"
TOOLS = REPO_ROOT / "templates" / "mcp-servers"

# Queries keyed to the six live MCP templates.
SUITE = [
    {"query": "Search the web and summarize GitHub issues for the project", "expected": "github"},
    {"query": "Find a page in the browser and capture the visible text", "expected": "browser"},
    {"query": "Store structured data in postgres and query rows", "expected": "postgres"},
    {"query": "Use slack to send a channel update about the release", "expected": "slack"},
    {"query": "Upload an artifact to object storage", "expected": "s3"},
    {"query": "Search the public web for recent docs", "expected": "web"},
]


def _distractors(n: int = 34) -> list[ToolRecord]:
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
    for i in range(n):
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
    cfg.allow_hash = True
    cfg.ensure_dirs()

    mem = build_memory_runtime(
        config=MemoryRuntimeConfig(store_root=scratch / "mem", provider="json", llm_mode="none")
    )
    router = build_router(cfg, start_sync=False, memory=mem)
    for tool in _distractors(34):
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
        top_tokens = sum(
            estimate_schema_tokens(t.schema or build_tool_schema(t.tool)) for t in result.tools
        )
        ratio = 0.0 if naive_tokens <= 0 else max(0.0, 1.0 - (top_tokens / naive_tokens))
        reductions.append(ratio)
        # Ensure serializer budget path is exercised.
        _ = serialize_tools_for_prompt(result.tools, max_tokens=max(64, top_tokens))
        rows.append(
            {
                "query": case["query"],
                "expected": case["expected"],
                "tool_ids": result.tool_ids,
                "hit": ok,
                "confidence_top1": result.confidence_top1,
                "high_confidence": result.high_confidence,
                "token_reduction_ratio": ratio,
                "candidate_count": result.candidate_count,
            }
        )

    emb_backend = router.embedder.backend_name
    router.shutdown()
    report = {
        "status": "ok",
        "tool_count": tool_count,
        "top_k": top_k,
        "cases": len(SUITE),
        "top3_accuracy": hits / max(1, len(SUITE)),
        "avg_token_reduction_ratio": sum(reductions) / max(1, len(reductions)),
        "naive_all_schema_tokens": naive_tokens,
        "embedding_backend": emb_backend,
        "rows": rows,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = run_mcpga()
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()
