#!/usr/bin/env python3
"""MAKS multi-agent dedup + sharing benchmark under realistic swarm load."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from neuroswarm_arm.runtime.maks import build_maks, load_maks_config
from neuroswarm_arm.runtime.maks.models import KVIdentity

DEFAULT_DOCS = REPO_ROOT / "benchmarks" / "test-data" / "docs.json"
DEFAULT_OUT = REPO_ROOT / "work" / "benchmarks" / "maks_multi_agent_dedup.json"

N_AGENTS = 8
M_PROMPTS = 20
TARGET_DOC_BYTES = 4096
NUM_DOCS = 20

SHARED_PREFIXES = [
    (
        "# System Prompt A\n"
        "You are a helpful research assistant. Follow safety guidelines. "
        "Cite sources when possible. Prefer concise answers.\n"
    ),
    (
        "# System Prompt B\n"
        "You are a code review agent. Analyze diffs for bugs, security, and style. "
        "Output actionable one-line comments.\n"
    ),
    (
        "# System Prompt C\n"
        "You are a planning agent for multi-step tasks. Decompose goals into "
        "ordered steps with clear dependencies.\n"
    ),
]


@dataclass(frozen=True, slots=True)
class PromptSpec:
    payload: bytes
    prefix: bytes
    prompt_hash: str


def _pad_markdown(title: str, body_seed: str, size: int) -> str:
    header = f"# {title}\n\n"
    paragraph = (
        f"{body_seed} This document supports MAKS dedup benchmarking. "
        "Repeated corpus text across agents should collapse under shared KV identity.\n\n"
    )
    chunks = [header]
    while sum(len(c) for c in chunks) < size:
        chunks.append(paragraph)
        chunks.append(f"- bullet {len(chunks)}: {body_seed} detail line.\n")
    text = "".join(chunks)
    if len(text) > size:
        return text[:size]
    return text + (" " * (size - len(text)))


def build_docs_corpus() -> dict[str, Any]:
    docs: list[dict[str, str]] = []
    for i in range(NUM_DOCS):
        title = f"Corpus Document {i + 1:02d}"
        body_seed = f"topic-{i}-axion-maks-bench"
        content = _pad_markdown(title, body_seed, TARGET_DOC_BYTES)
        docs.append({"id": f"doc-{i + 1:02d}", "title": title, "content": content})
    prefixes = [{"id": f"sys-{j + 1}", "text": p} for j, p in enumerate(SHARED_PREFIXES)]
    return {
        "version": 1,
        "target_doc_bytes": TARGET_DOC_BYTES,
        "docs": docs,
        "shared_prefixes": prefixes,
    }


def ensure_docs_json(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    corpus = build_docs_corpus()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(corpus, indent=2), encoding="utf-8")
    return corpus


def build_prompt_specs(corpus: dict[str, Any], *, prompts_per_agent: int) -> list[PromptSpec]:
    docs = corpus["docs"]
    prefixes = [p["text"] for p in corpus.get("shared_prefixes", [])]
    if not prefixes:
        prefixes = list(SHARED_PREFIXES)

    specs: list[PromptSpec] = []
    shared_count = prompts_per_agent // 2
    for idx in range(prompts_per_agent):
        doc = docs[idx % len(docs)]
        doc_text = doc["content"]
        if idx < shared_count:
            prefix_text = prefixes[idx % len(prefixes)]
            unique_tag = ""
        else:
            prefix_text = f"# Unique Agent Prefix {idx}\nSession scope: private.\n"
            unique_tag = f"\n## unique-slot-{idx}\n"

        full_text = prefix_text + unique_tag + doc_text
        payload = full_text.encode("utf-8")
        prefix_bytes = prefix_text.encode("utf-8")
        prompt_hash = hashlib.sha256(payload).hexdigest()[:16]
        specs.append(PromptSpec(payload=payload, prefix=prefix_bytes, prompt_hash=prompt_hash))
    return specs


async def _provider_used_bytes(mgr: Any) -> int:
    total = 0
    for prov in mgr.allocator.providers.values():
        stats = await prov.stats()
        total += int(stats.usage_bytes)
    return total


async def _collect_metrics(mgr: Any, handles: list[Any], per_agent_logical: dict[str, int]) -> dict[str, Any]:
    pool_stats = mgr.pool.stats()
    pages = int(pool_stats.get("pages", 0))
    shared_pages = int(pool_stats.get("shared_pages", 0))
    sharing_ratio = (shared_pages / pages) if pages else 0.0

    kv_ids = await mgr.registry.list_ids()
    refcount_gt1 = sum(1 for kv_id in kv_ids if mgr.refcount.get(kv_id) > 1)

    unique_kv_ids = len({h.kv_id for h in handles})
    return {
        "provider_used_bytes": await _provider_used_bytes(mgr),
        "allocator_used_bytes": int(mgr.allocator.used_bytes),
        "pool_used_bytes": int(pool_stats.get("used_bytes", 0)),
        "per_agent_logical_bytes": per_agent_logical,
        "dedup_ratio": round(float(mgr.dedup.stats.dedup_ratio), 4),
        "sharing_ratio": round(sharing_ratio, 4),
        "shared_pages": shared_pages,
        "pages": pages,
        "refcount_gt1": refcount_gt1,
        "unique_kv_ids": unique_kv_ids,
        "total_creates": len(handles),
        "ram_budget_bytes": int(mgr.config.ram_budget_bytes),
    }


async def _run_swarm(
    root: Path,
    *,
    dedup_enabled: bool,
    prompt_specs: list[PromptSpec],
    n_agents: int,
) -> dict[str, Any]:
    if dedup_enabled:
        os.environ.pop("NSA_MAKS_ENABLE_DEDUP", None)
        os.environ["NSA_MAKS_DEDUP"] = "1"
    else:
        os.environ["NSA_MAKS_ENABLE_DEDUP"] = "0"
        os.environ["NSA_MAKS_DEDUP"] = "0"

    root.mkdir(parents=True, exist_ok=True)
    cfg = load_maks_config(root)
    cfg.enable_dedup = dedup_enabled
    mgr = build_maks(cfg, enable_scheduler=False)
    identity = KVIdentity(model_id="llama-3.1-8b", quantization="q4_k_m")

    handles: list[Any] = []
    per_agent_logical: dict[str, int] = {}

    for i in range(n_agents):
        agent_id = f"a{i}"
        per_agent_logical[agent_id] = 0
        for spec in prompt_specs:
            h = await mgr.create(
                spec.payload,
                agent_id=agent_id,
                identity=identity,
                prompt_hash=spec.prompt_hash,
                prompt_prefix=spec.prefix,
            )
            handles.append(h)
            per_agent_logical[agent_id] += len(spec.payload)

    metrics = await _collect_metrics(mgr, handles, per_agent_logical)
    mgr.stop()
    metrics["dedup_enabled"] = dedup_enabled
    return metrics


def _pct_savings(control: int, dedup: int) -> float:
    if control <= 0:
        return 0.0
    return round(100.0 * (control - dedup) / control, 2)


def _summary_line(
    dedup_savings_pct: float,
    sharing_savings_pct: float,
    concurrent_agents: int,
    refcount_gt1: int,
) -> str:
    return (
        f"dedup_savings={dedup_savings_pct:.1f}% | "
        f"sharing={sharing_savings_pct:.1f}% | "
        f"agents@budget={concurrent_agents} | "
        f"refcount>1={refcount_gt1}"
    )


async def run(
    *,
    docs_path: Path,
    out_path: Path,
    n_agents: int,
    prompts_per_agent: int,
) -> dict[str, Any]:
    corpus = ensure_docs_json(docs_path)
    prompt_specs = build_prompt_specs(corpus, prompts_per_agent=prompts_per_agent)
    bench_root = out_path.parent / "maks_dedup_bench"

    dedup_run = await _run_swarm(
        bench_root / "dedup",
        dedup_enabled=True,
        prompt_specs=prompt_specs,
        n_agents=n_agents,
    )
    control_run = await _run_swarm(
        bench_root / "control",
        dedup_enabled=False,
        prompt_specs=prompt_specs,
        n_agents=n_agents,
    )

    control_mem = int(control_run["allocator_used_bytes"])
    dedup_mem = int(dedup_run["allocator_used_bytes"])
    dedup_savings_pct = _pct_savings(control_mem, dedup_mem)

    dedup_sharing = float(dedup_run["sharing_ratio"])
    control_sharing = float(control_run["sharing_ratio"])
    sharing_savings_pct = round(100.0 * max(0.0, dedup_sharing - control_sharing), 2)

    unique_kv = int(dedup_run["unique_kv_ids"]) or 1
    avg_kv_size = dedup_mem / unique_kv
    ram_budget = int(dedup_run["ram_budget_bytes"])
    concurrent_agents_supported = int(ram_budget / avg_kv_size) if avg_kv_size > 0 else 0

    summary_table = _summary_line(
        dedup_savings_pct,
        round(100.0 * dedup_sharing, 2),
        concurrent_agents_supported,
        int(dedup_run["refcount_gt1"]),
    )

    report: dict[str, Any] = {
        "status": "ok",
        "config": {
            "agents": n_agents,
            "prompts_per_agent": prompts_per_agent,
            "docs_path": str(docs_path),
            "identity": {"model_id": "llama-3.1-8b", "quantization": "q4_k_m"},
        },
        "dedup_run": dedup_run,
        "control_run": control_run,
        "dedup_savings_pct": dedup_savings_pct,
        "sharing_savings_pct": sharing_savings_pct,
        "avg_kv_size_bytes": round(avg_kv_size, 2),
        "concurrent_agents_supported": concurrent_agents_supported,
        "summary_table": summary_table,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="MAKS multi-agent dedup benchmark")
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--agents", type=int, default=N_AGENTS)
    parser.add_argument("--prompts", type=int, default=M_PROMPTS)
    args = parser.parse_args()

    report = asyncio.run(
        run(
            docs_path=args.docs,
            out_path=args.out,
            n_agents=args.agents,
            prompts_per_agent=args.prompts,
        )
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report["summary_table"])
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
