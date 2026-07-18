from __future__ import annotations

import os
import platform
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from .aqr import pick_quant
from .armora import ArmoraBudgetPolicy, build_armora, build_budget_service, build_rcis, build_rof, build_rpf
from .armora.profiling.arop_provider import ProfilingObservationProvider
from .armora.telemetry.bridges import (
    BudgetTelemetrySource,
    CallablePrometheusSource,
    MetricsStoreSource,
    RCISTelemetrySource,
    RPFTelemetrySource,
)
from .armora.telemetry.bridges.arop_provider import ROFObservationProvider
from .armora.telemetry.bridges.performix import PerformixMetricSource
from .armora.telemetry.middleware import ROFMiddleware
from .config import get_config
from .evolution import build_arop, load_arop_config
from .evolution.api import create_arop_router
from .evolution.performix_client import PerformixClient
from .gateway import AgentGateway
from .governor import ReasoningGovernor
from .inference.cascade import CascadeRouter
from .inference.llama_client import LlamaClient
from .metrics import metrics
from .metrics.bridges import PlaneMetricBridge, RMFObservationProvider
from .metrics.lifecycle import build_rmf
from .metrics.middleware import install_rmf_middleware
from .memory.mem0_client import build_memory
from .runtime.dipa import build_dipa
from .runtime.haoe import build_haoe
from .runtime.kv.api import create_kv_router
from .runtime.kv.factory import build_kv_runtime
from .runtime.kv.utils.config import KVRuntimeConfig
from .runtime.maks import build_maks, load_maks_config
from .runtime.dipa.cache.maks_connector import MAKSConnector
from .runtime.okf import build_okf
from .runtime.okf.api import create_okf_router
from .runtime.okf.factory import OKFConfig
from .runtime.acr import build_acr
from .runtime.rtg import build_rtg
from .runtime.rtg.hooks import DIPAReasoningHook
from .runtime.router import build_router, create_tool_router, load_router_config
from .schemas import ChatRequest
from .tools.registry import ToolRegistry
from .tools.semantic_mcp_router import SemanticMCPRouter


cfg = get_config()
router_cfg = load_router_config()
router_cfg.top_k = cfg.router_top_k
router_cfg.tool_metadata_root = cfg.tool_metadata_root
router_cfg.okf_root = cfg.okf_root
router_cfg.mem_store = cfg.mem_store

# Runtime Metrics Framework — owns metrics; Prometheus is exporter only
rmf = build_rmf()
metrics.bind(rmf)

tool_router = build_router(router_cfg, metrics_bridge=metrics, start_sync=True)
registry = ToolRegistry()
registry.bind(tool_router.registry)
semantic_router = SemanticMCPRouter(
    registry=registry,
    top_k=cfg.router_top_k,
)
semantic_router.bind(tool_router)

kv_cfg = KVRuntimeConfig(
    root=cfg.kv_store,
    block_size_tokens=cfg.kv_block_size,
    pressure_threshold=cfg.kv_pressure_threshold,
    ram_budget_bytes=cfg.kv_ram_budget,
    compression=cfg.kv_compression,
    redis_url=cfg.kv_redis_url,
    sharing_backend=cfg.kv_sharing_backend,
    enable_background_migration=cfg.kv_bg_migration,
)
kv_runtime = build_kv_runtime(kv_cfg, metrics_bridge=metrics)

maks_cfg = load_maks_config(cfg.kv_store)
maks_runtime = build_maks(
    maks_cfg,
    kv_runtime=kv_runtime,
    metrics_bridge=metrics,
    enable_scheduler=False,
)
maks_connector = MAKSConnector(sharing=maks_runtime)

# ARMORA Runtime Observability Framework — single telemetry control plane
rof = build_rof()
rof.register_metric_source(MetricsStoreSource(metrics))
rof.register_metric_source(PerformixMetricSource("work/haoe/performix_snapshot.json"))

# ARMORA Budget Envelope service — single per-process ledger; shared with MAKS policy
budget_service = build_budget_service(okf_root=cfg.okf_root)
rof.register_metric_source(BudgetTelemetrySource(budget_service))
# ARMORA Runtime Cost Intelligence System — learning signal (not admit gate)
rcis = build_rcis()
rof.register_metric_source(RCISTelemetrySource(rcis))
# ARMORA Runtime Profiling Framework — observation plane (not admit / not cost)
rpf = build_rpf()
rof.register_metric_source(RPFTelemetrySource(rpf))
_armora_policy = getattr(maks_runtime, "armora", None)
if isinstance(_armora_policy, ArmoraBudgetPolicy):
    _armora_policy.service = budget_service
elif _armora_policy is None:
    _armora_policy = ArmoraBudgetPolicy(service=budget_service)
    maks_runtime.armora = _armora_policy

memory = build_memory(cfg.mem_store)
if isinstance(_armora_policy, ArmoraBudgetPolicy):
    _armora_policy.memory = getattr(memory, "neuro", memory)

rtg = build_rtg(
    metrics_bridge=metrics,
    kv_pressure=maks_runtime,
    semantic_router=semantic_router,
    performix_path="work/haoe/performix_snapshot.json",
)
rtg_hook = DIPAReasoningHook(rtg, memory=getattr(memory, "neuro", memory))
governor = ReasoningGovernor(rtg=rtg)

dipa = build_dipa(
    metrics_bridge=metrics,
    tier_urls={
        "tier1": cfg.tier1_url,
        "tier2": cfg.tier2_url,
        "tier3": cfg.tier3_url,
    },
    topology_cores=None,
    maks=maks_connector,
    reasoning_hook=rtg_hook,
)
armora = build_armora(
    dipa.engine,
    budget=_armora_policy if isinstance(_armora_policy, ArmoraBudgetPolicy) else None,
)
# Bind DIPA afford gate to shared budget service
try:
    from neuroswarm_arm.armora.budget.dipa_gate import BudgetAffordGate

    _gate = BudgetAffordGate(budget_service)
    planner = getattr(getattr(dipa, "decision_engine", None), "planner", None) or getattr(
        dipa, "planner", None
    )
    if planner is not None and hasattr(planner, "bind_afford_gate"):
        planner.bind_afford_gate(_gate)
except Exception:
    pass
# Inject RCIS planner feedback port (repositories only — no planner mutation)
try:
    _de = getattr(dipa, "decision_engine", None)
    if _de is not None:
        _de.cost_feedback = rcis.feedback
        _de.profiler_feedback = rpf.feedback
except Exception:
    pass
# Compat cascade facade delegates to DIPA.
cascade = CascadeRouter(
    tier1=LlamaClient(cfg.tier1_url),
    tier2=LlamaClient(cfg.tier2_url),
    tier3=LlamaClient(cfg.tier3_url),
    governor=governor,
    confidence_threshold=cfg.cascade_confidence_threshold,
    kv_runtime=kv_runtime,
    dipa=dipa,
)
_affinity_cores = kv_runtime.block_manager.numa_policy.affinity_cores()
haoe = build_haoe(
    metrics_bridge=metrics,
    kv_pressure=maks_runtime.pressure_snapshot,
    fast_cores=_affinity_cores[:4] or list(range(4)),
    slow_cores=_affinity_cores[4:] or list(range(4, 8)),
    topology_cores=_affinity_cores or list(range(8)),
)
# HAOE locality → MAKS allocator hints
from neuroswarm_arm.runtime.maks.models import LocalityHint

maks_runtime.scheduler.set_locality(
    "default",
    LocalityHint(
        numa_node=0,
        affinity_cores=list(_affinity_cores or []),
        agent_id="default",
        priority=0,
    ),
)

okf_runtime = build_okf(
    OKFConfig(
        source_root=cfg.okf_root,
        artifact_root=cfg.okf_artifacts,
        token_budget=cfg.okf_token_budget,
        enabled=cfg.okf_enabled,
    ),
    metrics_bridge=metrics,
)

# Adaptive Context Runtime (ArmCascade Layer 4 Context OS) — wraps Mem0 + OKF
acr_runtime = build_acr(
    work_dir=Path("work/acr"),
    memory=getattr(memory, "neuro", memory),
    okf=okf_runtime if cfg.okf_enabled else None,
    metrics_bridge=metrics,
)

gateway = AgentGateway(
    registry=registry,
    semantic_router=semantic_router,
    cascade=cascade,
    dipa=dipa,
    kv_runtime=kv_runtime,
    haoe=haoe,
    tool_router=tool_router,
    armora_policy=_armora_policy,
    budget_service=budget_service,
    rcis=rcis,
    rpf=rpf,
    rof=rof,
    aqr_quant=pick_quant("tool_call"),
    inference_tier_hint=1,
    okf_runtime=okf_runtime,
    memory=memory,
    acr=acr_runtime,
)
performix = PerformixClient()

arop_cfg = load_arop_config(work_dir=Path("work/arop"), okf_root=cfg.okf_root)
arop = build_arop(
    arop_cfg,
    memory=memory,
    metrics_bridge=metrics,
    ascr=getattr(dipa, "ascr", None) or getattr(dipa, "cascade", None),
    rtg=rtg,
    router=tool_router,
    haoe=haoe,
    maks=maks_runtime,
    rcis=rcis,
)
try:
    arop.aggregator.add(ROFObservationProvider(rof))
except Exception:
    pass
try:
    arop.aggregator.add(ProfilingObservationProvider(rpf))
except Exception:
    pass
try:
    arop.aggregator.add(RMFObservationProvider(rmf))
except Exception:
    pass
# Late-bind KV / ACR / HAOE metric sources into ROF scrape registry
rof.register_metric_source(CallablePrometheusSource("kv", kv_runtime.telemetry))
try:
    rof.register_metric_source(
        CallablePrometheusSource("acr", acr_runtime, method="prometheus_text")
    )
except Exception:
    pass

# RMF plane bridges — normalize subsystem metrics into the registry
_rmf_bridges = PlaneMetricBridge(rmf)
_rmf_bridges.wire_budget(budget_service)
_rmf_bridges.wire_rcis(rcis)
_rmf_bridges.wire_haoe(haoe)
_rmf_bridges.wire_dipa(dipa)
_rmf_bridges.wire_maks(maks_runtime)
_rmf_bridges.wire_kv(kv_runtime)
try:
    _rmf_bridges.wire_acr(acr_runtime)
except Exception:
    pass
try:
    _awpp = getattr(dipa, "awpp", None) or getattr(dipa, "warm", None)
    if _awpp is not None:
        _rmf_bridges.wire_awpp(_awpp)
except Exception:
    pass
# ROF meter series only (not full ROF scrape — avoids RMF↔MetricsStore recursion)
rmf.register_source(rof.meter.export_prometheus)

app = FastAPI(title="NeuroSwarm-Arm", version="0.1.0")
app.add_middleware(ROFMiddleware, rof=rof)
install_rmf_middleware(app, rmf=rmf)
app.include_router(create_kv_router(kv_runtime))
from .runtime.maks.api import create_maks_router

app.include_router(create_maks_router(maks_runtime))
app.include_router(create_tool_router(tool_router))
app.include_router(create_arop_router(arop))
if cfg.okf_enabled:
    try:
        app.include_router(create_okf_router(okf_runtime.runtime))
    except Exception:
        pass

# Durable long-horizon workflows (Meta Orchestrator + checkpoint + experience)
from .runtime.swarm.api import (
    WorkflowService,
    create_experience_router,
    create_workflow_router,
)

workflow_service = WorkflowService(Path("work/swarm"))
app.include_router(create_workflow_router(workflow_service))
app.include_router(create_experience_router(workflow_service))


@app.on_event("shutdown")
def _shutdown_runtime() -> None:
    try:
        rmf.shutdown()
    except Exception:
        pass
    try:
        rof.shutdown()
    except Exception:
        pass
    try:
        rpf.shutdown()
    except Exception:
        pass
    tool_router.shutdown()
    haoe.shutdown()
    try:
        armora.shutdown()
    except Exception:
        dipa.shutdown()
    maks_runtime.stop()
    kv_runtime.shutdown()


@app.get("/health")
def health() -> dict[str, object]:
    mem_status: dict[str, object] = {"status": "unknown"}
    try:
        neuro = getattr(memory, "neuro", memory)
        if hasattr(neuro, "health"):
            hs = neuro.health()
            mem_status = {
                "healthy": bool(getattr(hs, "healthy", False)),
                "provider": getattr(hs, "provider", ""),
                "details": getattr(hs, "details", {}),
            }
    except Exception as exc:  # noqa: BLE001
        mem_status = {"healthy": False, "error": str(exc)}
    return {"status": "ok", "memory": mem_status}


@app.get("/ready")
def ready() -> dict[str, object]:
    """Always HTTP 200 — use body status ready|degraded so bootstrap curl -fsS never 500s."""
    try:
        models = {
            "tier1": {"path": cfg.model_tier1, "exists": Path(cfg.model_tier1).exists()},
            "tier2": {"path": cfg.model_tier2, "exists": Path(cfg.model_tier2).exists()},
            "tier3": {"path": cfg.model_tier3, "exists": Path(cfg.model_tier3).exists()},
        }
        try:
            health_payload = dipa.health()
            backends = health_payload.get("backends", health_payload) if isinstance(health_payload, dict) else {}
        except Exception:
            backends = {}
        llama_ready = {
            name: str(info.get("state", "unknown")) == "healthy"
            for name, info in backends.items()
            if isinstance(info, dict) and name.startswith("tier")
        }
        for tier in ("tier1", "tier2", "tier3"):
            llama_ready.setdefault(tier, False)
        try:
            tools_indexed = len(registry.as_list())
        except Exception:
            tools_indexed = 0
        reasons: list[str] = []
        for tier, model in models.items():
            if not model["exists"]:
                reasons.append(f"{tier} model missing: {model['path']}")
        for tier, is_ready in llama_ready.items():
            if not is_ready:
                reasons.append(f"{tier} llama server unavailable")
        if tools_indexed == 0:
            reasons.append(f"no tools indexed from {cfg.tool_metadata_root}")

        def _safe(label: str, fn):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"{label}: {exc}")
                return {"error": str(exc)}

        mem_details: dict[str, object] = {}
        try:
            neuro = getattr(memory, "neuro", memory)
            if hasattr(neuro, "health"):
                hs = neuro.health()
                mem_details = getattr(hs, "details", {}) or {}
        except Exception as exc:  # noqa: BLE001
            mem_details = {"error": str(exc)}

        system = {
            "arch": platform.machine(),
            "cpu_features": _cpu_features(),
            "expected_docker_network": bool(
                os.getenv("NSA_TIER1_URL") or os.getenv("NSA_TIER2_URL") or os.getenv("NSA_TIER3_URL")
            ),
        }
        dipa_status = _safe("dipa", dipa.status)
        router_health = _safe("router", tool_router.health)
        kv_status = _safe("kv", kv_runtime.status)
        haoe_status = _safe("haoe", haoe.status)
        rtg_status = _safe("rtg", rtg.status)
        okf_status = _safe("okf", okf_runtime.status) if cfg.okf_enabled else {"enabled": False}
        acr_status = _safe("acr", acr_runtime.health)
        arop_status = _safe("arop", arop.health)
        return {
            "status": "ready" if not reasons else "degraded",
            "system": system,
            "models": models,
            "llama": llama_ready,
            "dipa": dipa_status,
            "tools": {
                "indexed_count": tools_indexed,
                "metadata_root": str(cfg.tool_metadata_root),
                "router": router_health,
            },
            "kv": kv_status,
            "haoe": haoe_status,
            "rtg": rtg_status,
            "okf": okf_status,
            "acr": acr_status,
            "arop": arop_status,
            "memory": mem_details,
            "reasons": reasons,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "degraded",
            "reasons": [f"ready_handler: {exc}"],
            "error": str(exc),
        }


def _cpu_features() -> list[str]:
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return []
    text = cpuinfo.read_text(encoding="utf-8", errors="ignore")
    wanted = ("asimd", "sve", "sve2", "i8mm", "dotprod", "bf16")
    return sorted({flag for flag in wanted if re.search(rf"\b{re.escape(flag)}\b", text)})


@app.get("/v1/models")
def models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {"id": "cascade", "object": "model", "owned_by": "neuroswarm"},
            {"id": "tier1", "object": "model", "owned_by": "neuroswarm"},
            {"id": "tier2", "object": "model", "owned_by": "neuroswarm"},
            {"id": "tier3", "object": "model", "owned_by": "neuroswarm"},
        ],
    }


@app.get("/metrics")
def export_metrics(request: Request) -> Response:
    # RMF owns scrape; Prometheus is exporter only.
    if not rmf.check_auth(request.headers.get("Authorization")):
        raise HTTPException(status_code=401, detail="unauthorized")
    accept = request.headers.get("Accept", "")
    if "openmetrics" in accept:
        body, ctype = rmf.export("openmetrics")
    else:
        body, ctype = rmf.export("prometheus")
    mem = ""
    try:
        neuro = getattr(memory, "neuro", None)
        if neuro is not None and hasattr(neuro, "runtime"):
            mem = neuro.runtime.metrics.prometheus_text()
    except Exception:
        mem = ""
    arop_txt = ""
    try:
        from neuroswarm_arm.evolution.observation.otel_provider import PrometheusObservationProvider

        prom = next(
            (p for p in arop.aggregator.providers if isinstance(p, PrometheusObservationProvider)),
            None,
        )
        if prom is not None:
            snap = arop.aggregator.snapshot()
            arop_txt = prom.prometheus_text(dict(snap.aggregate))
    except Exception:
        arop_txt = ""
    # Never append after OpenMetrics `# EOF` — Prometheus rejects "unexpected data after # EOF".
    core = body.rstrip()
    if core.endswith("# EOF"):
        core = core[: -len("# EOF")].rstrip()
    extras = f"{mem}{arop_txt}".strip()
    if extras:
        payload = f"{core}\n{extras}\n"
    else:
        payload = f"{core}\n"
    if "openmetrics" in ctype or "openmetrics" in accept:
        payload = f"{payload.rstrip()}\n# EOF\n"
    return Response(content=payload, media_type=ctype)


@app.post("/v1/chat/completions")
def chat(req: ChatRequest) -> dict:
    response = gateway.handle_chat(req)
    return response.model_dump()


@app.get("/v1/cost/economics")
def cost_economics(limit: int = 200) -> dict:
    return rcis.unit_economics(limit=limit).model_dump()


@app.get("/v1/cost/comparisons")
def cost_comparisons(limit: int = 200) -> dict:
    return dict(rcis.comparison_bundle(limit=limit))


@app.get("/v1/cost/feedback/backends")
def cost_feedback_backends() -> dict:
    from neuroswarm_arm.armora.cost import WorkloadKey

    return rcis.feedback.lowest_cost_backend_sync(WorkloadKey()).model_dump()


@app.post("/bench/run")
def bench_run(payload: dict) -> dict:
    recipe = payload.get("recipe", "system-characterization")
    result = performix.run_recipe(recipe, output=cfg.benchmarks_dir / f"{recipe}.json")
    return result


def serve() -> None:
    import uvicorn

    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    serve()
