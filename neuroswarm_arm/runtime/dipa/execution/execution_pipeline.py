"""Execution pipeline — runs the mandatory lifecycle stages."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..interfaces.types import (
    ExecutionPhase,
    ExecutionPlan,
    GenerateRequest,
    GenerateResult,
    InferenceRequest,
    InferenceResponse,
    WorkloadClass,
)
from .execution_context import ExecutionContext
from .execution_graph import ExecutionGraph
from .execution_session import ExecutionSession
from .execution_state import advance

if TYPE_CHECKING:
    from ..kernel import DIPARuntime


class ExecutionPipeline:
    """Orchestrates planner → routers → cascade/backends → metrics."""

    def __init__(self, runtime: DIPARuntime) -> None:
        self.runtime = runtime

    def run(self, req: InferenceRequest) -> InferenceResponse:
        ctx = ExecutionContext(request=req, ids=req.ids)
        session = ExecutionSession(ctx=ctx, session_id=req.session_id or "")
        self.runtime.state.enter_session()
        self.runtime.state.bump_request()
        t0 = time.monotonic()
        try:
            from neuroswarm_arm.armora.telemetry.runtime import get_rof
            from neuroswarm_arm.armora.telemetry.schemas import SpanNames

            rof = get_rof()
            if rof is not None and rof.config.enabled:
                with rof.span(SpanNames.DIPA_INFER):
                    with rof.span(SpanNames.PLANNER):
                        plan = self._plan(ctx)
                    ctx.plan = plan
                    ctx.mark(advance(ctx.phase, ExecutionPhase.PLANNED))
                    with rof.span(SpanNames.ROUTING):
                        result = self._execute_plan(ctx, plan)
                    response = self._to_response(req, plan, result, ctx, t0)
                    return session.finish(response)
            plan = self._plan(ctx)
            ctx.plan = plan
            ctx.mark(advance(ctx.phase, ExecutionPhase.PLANNED))
            result = self._execute_plan(ctx, plan)
            response = self._to_response(req, plan, result, ctx, t0)
            return session.finish(response)
        except Exception as exc:  # noqa: BLE001 — recovery boundary
            ctx.errors.append(str(exc))
            ctx.mark(ExecutionPhase.RECOVERING)
            try:
                import logging
                from pathlib import Path
                import traceback

                logging.getLogger("neuroswarm.dipa").exception("dipa execute failed: %s", exc)
                Path("work/arop").mkdir(parents=True, exist_ok=True)
                Path("work/arop/last_dipa_exc.txt").write_text(
                    f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                    encoding="utf-8",
                )
            except Exception:
                pass
            recovered = self.runtime.recovery.handle_failure(req, ctx, exc)
            if recovered is not None:
                # Still record DIPA request metrics so /metrics is not empty on recovery.
                try:
                    plan = ctx.plan
                    self.runtime.metrics.record_inference(
                        latency_ms=(time.monotonic() - t0) * 1000.0,
                        ttft_ms=float((recovered.metrics or {}).get("latency_ms") or 0.0),
                        tier=int(recovered.tier_used or 0),
                        quant=str(getattr(recovered, "quant", "") or (plan.quant if plan else "")),
                        backend=str(getattr(recovered, "backend", "") or ""),
                        workload=str(
                            getattr(getattr(plan, "workload", None), "value", None)
                            or getattr(plan, "workload", "")
                            or "unknown"
                        ),
                        prompt_tokens=int(recovered.prompt_tokens or 0),
                        completion_tokens=int(recovered.completion_tokens or 0),
                    )
                except Exception:
                    pass
                return session.finish(recovered)
            ctx.mark(ExecutionPhase.FAILED)
            raise
        finally:
            self.runtime.state.leave_session()

    def _plan(self, ctx: ExecutionContext) -> ExecutionPlan:
        return self.runtime.decision_engine.decide(ctx.request)

    def _execute_plan(
        self, ctx: ExecutionContext, plan: ExecutionPlan
    ) -> GenerateResult:
        rt = self.runtime
        req = ctx.request

        # RTG admit (AIM Pillar 4) — DIPA asks via IReasoningHook port only.
        rtg_meta = rt.reasoning_hook.on_admit(
            req,
            tool_confidence=req.tool_confidence,
            tool_names=req.tool_names,
            slo_remaining_ms=req.latency_sla_ms,
            workflow_type=str(getattr(plan.workload, "value", plan.workload) or "chat"),
        )
        if rtg_meta:
            cap = rtg_meta.get("thinking_token_cap")
            if cap is not None:
                req.thinking_token_cap = int(cap)
                req.max_tokens = min(req.max_tokens, int(cap))
            system = rtg_meta.get("system_prompt") or ""
            if system and not req.system_prompt:
                req.system_prompt = str(system)
            demand = float(rtg_meta.get("governor_accuracy_demand", 0.0) or 0.0)
            if demand:
                req.baggage["governor_accuracy_demand"] = demand
            rtg_session = str(rtg_meta.get("session_id") or req.session_id or "")
            if rtg_session:
                req.baggage["rtg_session_id"] = rtg_session
            force_msg = str(rtg_meta.get("force_close_message") or "")
            if force_msg:
                req.baggage["rtg_force_close_message"] = force_msg

        # classify / intent already embedded in plan
        ctx.mark(ExecutionPhase.CLASSIFIED)
        ctx.mark(ExecutionPhase.INTENT_DETECTED)
        ctx.model_name = plan.model
        ctx.mark(ExecutionPhase.MODEL_SELECTED)
        ctx.backend_name = plan.backend
        ctx.mark(ExecutionPhase.BACKEND_SELECTED)

        topo = rt.topology_router.probe(plan)
        plan.affinity_cores = list(topo.get("affinity_cores", []))
        plan.numa_node = int(topo.get("numa_node", 0))
        plan.device_class = topo.get("device_class", plan.device_class)
        ctx.mark(ExecutionPhase.HARDWARE_PROBED)
        ctx.mark(ExecutionPhase.POLICY_APPLIED)

        # AQR may consume governor accuracy demand from baggage
        if "governor_accuracy_demand" in req.baggage:
            plan.metadata["governor_accuracy_demand"] = req.baggage[
                "governor_accuracy_demand"
            ]

        quant = rt.quant_router.resolve(req, plan)
        plan.quant = quant
        ctx.quant = quant
        ctx.mark(ExecutionPhase.QUANT_RESOLVED)

        warm = rt.warm_manager.ensure(req, plan)
        ctx.warm = warm
        ctx.mark(ExecutionPhase.WARM_CHECKED)

        kv_handle = rt.kv_loader.load_sync(req.session_id, req.agent_id)
        ctx.kv_handle = kv_handle
        ctx.mark(ExecutionPhase.KV_ATTACHED)

        # Prefill/decode soft path (ADR-0006); fall back to cascade/fused on failure.
        if plan.pd_enabled and self._pd_ready(rt):
            try:
                result = self._run_pd(ctx, plan, kv_handle)
            except Exception as exc:  # noqa: BLE001
                ctx.errors.append(f"pd_fallback:{exc}")
                plan.pd_enabled = False
                plan.metadata["pd_fallback"] = str(exc)
                result = self._run_fused_or_cascade(ctx, plan, req, kv_handle)
        else:
            result = self._run_fused_or_cascade(ctx, plan, req, kv_handle)

        # Streaming control tick on completed text (chunk-level for HTTP backends)
        rtg_sid = str(req.baggage.get("rtg_session_id") or req.session_id or "")
        if rtg_sid and result.text:
            decision = rt.reasoning_hook.on_chunk(
                rtg_sid,
                result.text,
                tokens=max(1, result.completion_tokens or len(result.text.split())),
                latency_ms=float(result.latency_ms or 0.0),
                cascade_tier=int(result.tier_used or plan.cascade_start_tier or 1),
                model_confidence=float(result.metrics.get("confidence", 0.0) or 0.0),
            )
            result.metrics["rtg_action"] = 1.0 if decision.get("terminal") else 0.0
            result.metrics["rtg_force_close"] = 1.0 if decision.get("force_close") else 0.0
            if decision.get("escalate_to_tier") and int(decision["escalate_to_tier"]) > int(
                result.tier_used or 1
            ):
                escalate_tier = int(decision["escalate_to_tier"])
                if plan.use_cascade and escalate_tier > int(result.tier_used or 1):
                    plan.cascade_start_tier = escalate_tier
                    escalated = rt._run_async(rt.cascade_engine.run(req, plan, ctx))
                    result = escalated
            if decision.get("force_close") and decision.get("force_close_message"):
                close = str(decision["force_close_message"])
                if close and close not in result.text:
                    result = GenerateResult(
                        text=result.text.rstrip() + "\n" + close,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        latency_ms=result.latency_ms,
                        ttft_ms=result.ttft_ms,
                        backend=result.backend,
                        model=result.model,
                        quant=result.quant,
                        tier_used=result.tier_used,
                        raw=result.raw,
                        metrics=result.metrics,
                    )
            rt.reasoning_hook.on_complete(rtg_sid, result.text)

        ctx.mark(ExecutionPhase.STREAMING)
        if plan.stream and result.text:
            rt.stream_manager.publish_complete(req.session_id, result.text)

        rt.kv_writer.save_sync(
            req.session_id,
            result.text.encode("utf-8")[:4096],
            agent_id=req.agent_id,
            metadata={
                "model_id": result.model or plan.model or req.model,
                "model": result.model or plan.model or req.model,
                "quantization": plan.quant,
                "quant": plan.quant,
                "prompt_hash": "",
                "priority": 0,
            },
        )
        ctx.mark(ExecutionPhase.METRICS)
        return result

    def _pd_ready(self, rt: Any) -> bool:
        return (
            getattr(rt, "prefill_manager", None) is not None
            and getattr(rt, "decode_manager", None) is not None
            and getattr(rt, "kv_transfer", None) is not None
            and getattr(rt, "chunk_planner", None) is not None
            and getattr(rt, "chunk_executor", None) is not None
        )

    def _run_pd(
        self,
        ctx: ExecutionContext,
        plan: ExecutionPlan,
        kv_handle: str | None,
    ) -> GenerateResult:
        rt = self.runtime
        req = ctx.request
        messages = self._messages(req)
        chunk_size = int(getattr(rt.config, "chunk_size", 2048) or 2048)
        chunks = rt.chunk_planner.plan(req, chunk_size=chunk_size)
        # Use full messages for final decode handoff.
        for ch in chunks:
            if ch.index == ch.total - 1:
                ch.messages = messages

        ctx.mark(ExecutionPhase.PREFILL)
        mode = plan.transfer_mode
        results = rt._run_async(
            rt.chunk_executor.run(
                chunks,
                ctx=ctx,
                session_id=req.session_id,
                quant=plan.quant,
                kv_handle=kv_handle,
                transfer_mode=mode,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        )
        if rt.batch_scheduler is not None:
            rt.batch_scheduler.record(len(chunks))
            rt.metrics.set("dipa_batch_size", float(len(chunks)))
            rt.metrics.set("dipa_chunk_count", float(len(chunks)))

        with rt.otel.span("dipa.kv_transfer", mode=mode.value):
            handle = rt._run_async(
                rt.kv_transfer.handoff(
                    results,
                    messages=messages,
                    decode_backend=plan.decode_backend or "llama_cpp",
                    session_id=req.session_id,
                    quant=plan.quant,
                )
            )
        # Prefer selected cascade model tier as decode target when registered.
        if plan.model and rt.backends.get(plan.model) is not None:
            handle.decode_backend = plan.model
        elif plan.decode_backend == "llama_cpp" and rt.backends.get("llama_cpp") is None:
            handle.decode_backend = plan.model or "tier2"

        ctx.mark(ExecutionPhase.DECODE)
        result = rt._run_async(
            rt.decode_manager.generate_from_handle(
                handle,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                ctx=ctx,
            )
        )
        result.metrics = dict(result.metrics)
        result.metrics["pd_enabled"] = 1.0
        result.metrics["pd_mode"] = {
            "off": 0.0,
            "soft": 1.0,
            "native": 2.0,
        }.get(plan.pd_mode.value, 0.0)
        return result

    def _run_fused_or_cascade(
        self,
        ctx: ExecutionContext,
        plan: ExecutionPlan,
        req: InferenceRequest,
        kv_handle: str | None,
    ) -> GenerateResult:
        rt = self.runtime
        if plan.use_cascade:
            ctx.mark(ExecutionPhase.CASCADE)
            return rt._run_async(rt.cascade_engine.run(req, plan, ctx))
        ctx.mark(ExecutionPhase.PREFILL)
        backend = rt.backends.get(plan.backend)
        if backend is None:
            raise RuntimeError(f"backend unavailable: {plan.backend}")
        gen_req = GenerateRequest(
            messages=self._messages(req),
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            session_id=req.session_id,
            quant=plan.quant,
            stream=plan.stream,
            kv_handle=kv_handle,
            speculative=plan.speculation,
        )
        result = rt._run_async(backend.generate(gen_req, ctx))
        ctx.mark(ExecutionPhase.DECODE)
        return result

    def _messages(self, req: InferenceRequest) -> list[dict[str, str]]:
        messages = list(req.messages)
        system_parts: list[str] = []
        if req.system_prompt:
            system_parts.append(req.system_prompt)
        # Semantic MCP Tool Router: inject only top-K schemas (never full catalog).
        if req.tool_prompt_block:
            system_parts.append(req.tool_prompt_block)
        elif req.tool_schemas:
            import json

            system_parts.append(
                "Available tools (semantic top-k only). Prefer these tools when applicable:\n"
                + json.dumps(req.tool_schemas, indent=2)
            )
        elif req.tool_names:
            system_parts.append(
                "Preferred tools for this request: " + ", ".join(req.tool_names)
            )
        if system_parts:
            messages = [{"role": "system", "content": "\n\n".join(system_parts)}] + messages
        return messages

    def _to_response(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan,
        result: GenerateResult,
        ctx: ExecutionContext,
        t0: float,
    ) -> InferenceResponse:
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        metrics: dict[str, float | str] = {
            "latency_ms": elapsed_ms,
            "ttft_ms": result.ttft_ms,
            "tier_used": float(result.tier_used),
            "quant_policy": plan.quant,
            "backend": result.backend or plan.backend,
            "model": result.model or plan.model,
            "warm": 1.0 if ctx.warm else 0.0,
            "prompt_tokens": float(result.prompt_tokens),
            "completion_tokens": float(result.completion_tokens),
            "workload": plan.workload.value,
            "tool_schema_count": float(len(req.tool_schemas) or len(req.tool_names)),
            "tool_confidence": float(req.tool_confidence),
            "pd_enabled": 1.0 if plan.pd_enabled else 0.0,
            "kv_transfer_mode": plan.transfer_mode.value,
        }
        metrics.update({k: float(v) if isinstance(v, (int, float)) else v for k, v in result.metrics.items()})
        self.runtime.metrics.record_inference(
            latency_ms=elapsed_ms,
            ttft_ms=result.ttft_ms,
            tier=result.tier_used,
            quant=plan.quant,
            backend=plan.backend,
            workload=plan.workload.value,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )
        return InferenceResponse(
            text=result.text,
            model=req.model or plan.model,
            tier_used=result.tier_used,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            thinking_token_cap=req.thinking_token_cap or 0,
            tool_schemas_used=list(req.tool_names),
            quant=plan.quant,
            backend=result.backend or plan.backend,
            plan=plan,
            metrics=metrics,
            degraded=False,
        )
