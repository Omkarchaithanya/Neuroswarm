from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import time
import json
import os
import platform
import sys

# Make the repo root importable when benchmark scripts are launched directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from neuroswarm_arm.governor import ReasoningGovernor
from neuroswarm_arm.inference.cascade import CascadeRouter
from neuroswarm_arm.runtime.memory import build_memory_runtime
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig
from neuroswarm_arm.runtime.router import build_router as build_runtime_router, load_router_config
from neuroswarm_arm.runtime.router.benchmarks import run_router_benchmark, write_benchmark
from neuroswarm_arm.schemas import ChatRequest, Message, PlanState
from neuroswarm_arm.tools.registry import ToolRegistry
from neuroswarm_arm.tools.semantic_mcp_router import SemanticMCPRouter


DEFAULT_TOOL_ROOT = REPO_ROOT / "templates" / "mcp-servers"
DEFAULT_RESULTS_DIR = REPO_ROOT / "work" / "benchmarks"


@dataclass(slots=True)
class MockLlamaClient:
    responses: dict[str, str]
    default: str

    def chat(self, messages: list[dict], max_tokens: int = 512, temperature: float = 0.2) -> dict:
        prompt = "\n".join(m.get("content", "") for m in messages if isinstance(m, dict))
        lowered = prompt.lower()
        for key, value in self.responses.items():
            if key in lowered:
                return {"choices": [{"message": {"content": value[:max_tokens]}}]}
        return {"choices": [{"message": {"content": self.default[:max_tokens]}}]}


def load_registry(tool_root: Path = DEFAULT_TOOL_ROOT) -> ToolRegistry:
    registry = ToolRegistry()
    if tool_root.exists():
        registry.load_okf_metadata(tool_root)
    return registry


def build_router(tool_root: Path = DEFAULT_TOOL_ROOT, top_k: int = 3) -> SemanticMCPRouter:
    cfg = load_router_config(REPO_ROOT)
    cfg.tool_metadata_root = tool_root
    cfg.top_k = top_k
    cfg.enable_hot_reload = False
    cfg.ann_backend = os.getenv("NSA_ROUTER_ANN_BACKEND", "exact")
    # Benchmarks are CI-friendly: allow hash when ST/ONNX are unavailable.
    cfg.allow_hash = True
    os.environ.setdefault("NSA_ROUTER_ALLOW_HASH", "1")
    mem_root = REPO_ROOT / "work" / "benchmarks" / ".mem"
    offline_mem = build_memory_runtime(
        config=MemoryRuntimeConfig(
            store_root=mem_root,
            provider="json",
            llm_mode="none",
        )
    )
    inner = build_runtime_router(cfg, start_sync=False, memory=offline_mem)
    registry = ToolRegistry()
    registry.bind(inner.registry)
    facade = SemanticMCPRouter(registry=registry, top_k=top_k)
    facade.bind(inner)
    return facade


def tool_query_suite() -> list[dict[str, object]]:
    return [
        {"query": "Search the web and summarize GitHub issues for the project", "expected": "github"},
        {"query": "Find a page in the browser and capture the visible text", "expected": "browser"},
        {"query": "Store structured data in postgres and query rows", "expected": "postgres"},
        {"query": "Use slack to send a channel update about the release", "expected": "slack"},
        {"query": "Upload an artifact to object storage", "expected": "s3"},
        {"query": "Look up a related web source before answering", "expected": "web-search"},
    ]


def evaluate_router(tool_root: Path = DEFAULT_TOOL_ROOT, top_k: int = 3) -> dict[str, object]:
    facade = build_router(tool_root, top_k=top_k)
    assert facade.inner is not None
    result = run_router_benchmark(facade.inner, cases=tool_query_suite())
    return {
        "status": result["status"],
        "top1_accuracy": result["top1_accuracy"],
        "top3_accuracy": result["top3_accuracy"],
        "top5_accuracy": result.get("top5_accuracy"),
        "latency_ms": result.get("latency_ms"),
        "avg_token_reduction": result.get("avg_token_reduction"),
        "ann_backend": result.get("ann_backend"),
        "cases": result.get("cases"),
        "full": result,
    }


def evaluate_governor() -> dict[str, object]:
    from neuroswarm_arm.runtime.rtg import build_rtg

    rtg = build_rtg()
    governor = ReasoningGovernor(rtg=rtg)
    legacy = ReasoningGovernor()
    scenarios = [
        PlanState(tool_confidence_top1=0.95, kv_pressure=0.20, slo_remaining_ms=8000, self_consistency_score=0.10),
        PlanState(tool_confidence_top1=0.60, kv_pressure=0.80, slo_remaining_ms=5000, self_consistency_score=0.20),
        PlanState(tool_confidence_top1=0.40, kv_pressure=0.20, slo_remaining_ms=2500, self_consistency_score=0.15),
        PlanState(tool_confidence_top1=0.88, kv_pressure=0.10, slo_remaining_ms=3000, self_consistency_score=0.93),
    ]
    caps = [governor.cap(plan) for plan in scenarios]
    legacy_caps = [legacy.cap(plan) for plan in scenarios]
    return {
        "status": "ok",
        "caps": caps,
        "legacy_caps": legacy_caps,
        "mean_cap": sum(caps) / len(caps),
        "mean_legacy_cap": sum(legacy_caps) / len(legacy_caps),
        "rtg_enabled": True,
    }


def evaluate_cascade() -> dict[str, object]:
    from neuroswarm_arm.runtime.rtg import build_rtg

    clients = {
        "tier1": MockLlamaClient({"github": "use github tool"}, "tier1"),
        "tier2": MockLlamaClient({}, "tier2"),
        "tier3": MockLlamaClient({}, "tier3"),
    }
    router = CascadeRouter(
        tier1=clients["tier1"],
        tier2=clients["tier2"],
        tier3=clients["tier3"],
        governor=ReasoningGovernor(rtg=build_rtg()),
    )
    req = ChatRequest(messages=[Message(role="user", content="github issues please")])
    resp = router.handle(req, ["github"])
    return {"status": "ok", "tier_used": resp.tier_used, "content": resp.content}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def host_fingerprint() -> dict[str, object]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
        "ts": time(),
    }


def system_snapshot() -> dict[str, object]:
    """Capture host + repo context for benchmark result bundles."""
    snap = host_fingerprint()
    snap["repo_root"] = str(REPO_ROOT)
    snap["cwd"] = str(Path.cwd())
    try:
        import psutil

        vm = psutil.virtual_memory()
        snap["cpu_count"] = psutil.cpu_count(logical=True)
        snap["memory_total_mb"] = round(vm.total / (1024 * 1024), 2)
        snap["memory_available_mb"] = round(vm.available / (1024 * 1024), 2)
    except Exception:  # noqa: BLE001
        pass
    return snap


def estimate_economics(
    router: dict[str, object],
    governor: dict[str, object],
    cascade: dict[str, object],
) -> dict[str, object]:
    """Aggregate router, governor, and cascade dry-run metrics into one scorecard."""
    top3 = float(router.get("top3_accuracy") or 0.0)
    top1 = float(router.get("top1_accuracy") or 0.0)
    token_reduction = float(router.get("avg_token_reduction") or 0.0)
    mean_cap = float(governor.get("mean_cap") or 0.0)
    legacy_cap = float(governor.get("mean_legacy_cap") or 0.0)
    tier_used = cascade.get("tier_used")
    savings_score = round(
        (top3 * 0.35) + (token_reduction * 0.25) + (min(mean_cap, 4096) / 4096 * 0.20) + (top1 * 0.20),
        4,
    )
    return {
        "status": "ok",
        "router_top1_accuracy": top1,
        "router_top3_accuracy": top3,
        "router_avg_token_reduction": token_reduction,
        "governor_mean_cap": mean_cap,
        "governor_mean_legacy_cap": legacy_cap,
        "governor_cap_delta": round(mean_cap - legacy_cap, 2),
        "cascade_tier_used": tier_used,
        "estimated_savings_score": savings_score,
    }
