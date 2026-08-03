"""Integration adapters — gateway handlers without circular imports."""

from __future__ import annotations

from typing import Any, Callable, Protocol
from uuid import uuid4

import anyio

from ..execution.execution_context import ExecutionContext
from ..interfaces.types import CorrelationIds


class SupportsRoute(Protocol):
    def route(self, query: str, *args: Any, **kwargs: Any) -> Any: ...


class SupportsCascade(Protocol):
    """Legacy cascade / DIPA-compatible inference handle."""

    def handle(self, req: Any, tool_names: list[str] | None = None, **kwargs: Any) -> Any: ...


# Alias — HAOE injects DIPA via the same handle() contract.
SupportsInference = SupportsCascade


class SupportsKV(Protocol):
    def create_session(self, session_id: str, agent_id: str = "") -> Any: ...

    async def allocate(
        self, session_id: str, payload: bytes, agent_id: str = ""
    ) -> Any: ...

    async def checkpoint(self, session_id: str) -> Any: ...


def build_chat_handlers(
    *,
    semantic_router: SupportsRoute,
    cascade: SupportsCascade | None = None,
    inference: SupportsInference | None = None,
    kv_runtime: SupportsKV | None,
    request: Any,
    route_context_factory: Callable[[Any, str], Any] | None = None,
    okf_runtime: Any | None = None,
    memory: Any | None = None,
    acr: Any | None = None,
) -> dict[str, Callable[[ExecutionContext], Any]]:
    """Build injected callables for the chat workflow DAG.

    ``inference`` (DIPA) preferred; ``cascade`` kept for backward compatibility.
    Optional ``acr`` (Adaptive Context Runtime) owns context assembly when enabled.
    Fallback: ``okf_runtime`` / ``memory`` Mem0→OKF→route→tool-docs path.
    """

    engine = inference or cascade
    if engine is None:
        raise ValueError("build_chat_handlers requires inference or cascade")

    state: dict[str, Any] = {
        "tool_names": [],
        "tool_schemas": [],
        "tool_confidence": 0.0,
        "tool_high_confidence": False,
        "tool_prompt_block": "",
        "session_id": getattr(request, "session_id", None) or f"chat-{uuid4().hex[:16]}",
        "response": None,
        "mem0_facts": [],
        "okf_knowledge": None,
        "okf_merged_context": "",
        "acr_snapshot": None,
    }

    def _acr_enabled() -> bool:
        return acr is not None and bool(getattr(acr, "enabled", False))

    def _query_text() -> str:
        messages = getattr(request, "messages", None) or []
        if messages:
            return getattr(messages[-1], "content", "") or ""
        return ""

    def _agent_profile() -> str:
        role = str(getattr(request, "agent_role", "") or "architect").lower()
        if "research" in role:
            return "research"
        if "code" in role or "tool" in role:
            return "coding"
        if "review" in role:
            return "reviewer"
        if "plan" in role:
            return "planner"
        return "architect"

    def _neuro():
        """Resolve NeuroMemory façade from injected memory (shim or runtime)."""
        if memory is None:
            return None
        if hasattr(memory, "recall") and hasattr(memory, "remember_success"):
            return memory
        return getattr(memory, "neuro", None) or getattr(memory, "_memory", None)

    def mem0_recall(ctx: ExecutionContext) -> list[str]:
        # When ACR enabled, understanding+retrieval happen in okf_tool_docs assembly.
        # Keep light recall for baggage/compat when ACR off or as prefetch signal.
        facts: list[str] = []
        agent_id = getattr(request, "agent_id", "") or ctx.ids.agent_id or "default"
        if _acr_enabled():
            state["mem0_facts"] = facts
            ctx.baggage["mem0_facts"] = facts
            ctx.baggage["acr_prefetch"] = True
            return facts
        neuro = _neuro()
        original_query = _query_text() or "context"
        # Router-biased query when RoutingResult present (L4 Mem0 wiring).
        router_result = ctx.baggage.get("router_result")
        query = original_query
        if router_result is not None:
            tools = list(getattr(router_result, "tools", None) or [])
            bias_names: list[str] = []
            for scored in tools[:5]:
                tool = getattr(scored, "tool", scored)
                name = getattr(tool, "name", None) or getattr(scored, "name", None)
                if name:
                    bias_names.append(str(name))
            if bias_names:
                query = f"{original_query} {' '.join(bias_names)}".strip()
        try:
            if neuro is not None:
                # Pull reflections before planning/cascade for planner learning
                reflections = list(
                    neuro.recall(agent_id, _query_text() or "reflection", limit=3, namespace="reflection/")
                    or []
                )
                facts = list(neuro.recall(agent_id, query, limit=5) or [])
                if reflections:
                    facts = reflections + facts
            elif memory is not None:
                facts = list(memory.search(agent_id, query, limit=5) or [])
        except Exception:
            facts = []
        state["mem0_facts"] = facts
        ctx.baggage["mem0_facts"] = facts
        return facts

    def okf_context(ctx: ExecutionContext) -> str:
        if _acr_enabled():
            # Institutional knowledge loaded inside ACR build_context
            ctx.baggage["okf_tokens"] = 0
            ctx.baggage["okf_knowledge"] = ""
            return ""
        if okf_runtime is None:
            return ""
        knowledge = okf_runtime.query(_query_text() or "nexus overview", agent_profile=_agent_profile())
        state["okf_knowledge"] = knowledge
        ctx.baggage["okf_tokens"] = int(getattr(knowledge, "tokens_used", 0) or 0)
        ctx.baggage["okf_knowledge"] = getattr(knowledge, "text", "") or ""
        return getattr(knowledge, "text", "") or ""

    def semantic_route(ctx: ExecutionContext) -> list[str]:
        query = ""
        messages = getattr(request, "messages", None) or []
        if messages:
            query = getattr(messages[-1], "content", "") or ""
        route_ctx = None
        if route_context_factory is not None:
            route_ctx = route_context_factory(request, query)
        elif hasattr(semantic_router, "build_context"):
            try:
                route_ctx = semantic_router.build_context(request, query)
            except Exception:
                route_ctx = None

        # Prefer full RoutingResult when available
        result = None
        if hasattr(semantic_router, "route_result"):
            result = semantic_router.route_result(query, context=route_ctx)
        else:
            routed = semantic_router.route(query, context=route_ctx) if route_ctx is not None else semantic_router.route(query)
            if hasattr(routed, "tools") and hasattr(routed, "confidence_top1"):
                result = routed
            else:
                names = []
                for t in routed:
                    names.append(getattr(t, "name", str(t)))
                state["tool_names"] = names
                ctx.baggage["tool_names"] = names
                return names

        names = list(result.tool_names)
        schemas = list(result.schemas)
        prompt_block = ""
        if hasattr(semantic_router, "prompt_block"):
            try:
                prompt_block = semantic_router.prompt_block(result)
            except Exception:
                prompt_block = ""
        # Explicit cost-router hints (tier start) for DecisionEngine + metrics.
        try:
            from neuroswarm_arm.runtime.router.orchestration import build_routed_inference_hints

            hints = build_routed_inference_hints(
                query,
                result,
                prompt_block=prompt_block,
                schemas=schemas,
            )
            names = list(hints.tool_names) or names
            schemas = list(hints.tool_schemas) or schemas
            prompt_block = hints.tool_prompt_block or prompt_block
            state["cost_router"] = hints.cost_decision.as_dict() if hints.cost_decision else {}
            state["schema_token_reduction"] = float(hints.schema_token_reduction)
            ctx.baggage["cost_router"] = state["cost_router"]
            ctx.baggage["schema_token_reduction"] = state["schema_token_reduction"]
            ctx.baggage["routed_hints"] = hints.as_dict()
        except Exception:
            state["cost_router"] = {}
        high_conf = bool(getattr(result, "high_confidence", False))
        thinking_budget = None
        cfg = getattr(semantic_router, "config", None)
        if cfg is not None:
            thinking_budget = int(getattr(cfg, "high_conf_thinking_budget", 256) or 256)
        state["tool_names"] = names
        state["tool_schemas"] = schemas
        state["tool_confidence"] = float(result.confidence_top1)
        state["tool_high_confidence"] = high_conf
        state["high_conf_thinking_budget"] = thinking_budget
        state["tool_prompt_block"] = prompt_block
        ctx.baggage["tool_names"] = names
        ctx.baggage["tool_schemas"] = schemas
        ctx.baggage["tool_confidence"] = float(result.confidence_top1)
        ctx.baggage["tool_high_confidence"] = high_conf
        if thinking_budget is not None:
            ctx.baggage["high_conf_thinking_budget"] = thinking_budget
        ctx.baggage["tool_prompt_block"] = prompt_block
        # Full RoutingResult object for downstream pillars (not just to_dict).
        ctx.baggage["router_result"] = result
        ctx.baggage["routing_result"] = result.to_dict() if hasattr(result, "to_dict") else result
        # Re-bias Mem0 after route (DAG runs mem0 before route; refresh when router hits).
        if not _acr_enabled():
            neuro = _neuro()
            if neuro is not None:
                try:
                    agent_id = getattr(request, "agent_id", "") or ctx.ids.agent_id or "default"
                    bias = " ".join(
                        str(getattr(getattr(s, "tool", s), "name", "") or getattr(s, "name", "") or "")
                        for s in list(getattr(result, "tools", None) or [])[:5]
                    ).strip()
                    q = f"{query} {bias}".strip() if bias else (query or "context")
                    facts = list(neuro.recall(agent_id, q, limit=5) or [])
                    if facts:
                        state["mem0_facts"] = facts
                        ctx.baggage["mem0_facts"] = facts
                except Exception:
                    pass
        return names

    def tool_search_activation(ctx: ExecutionContext) -> str:
        """Hermes tool_search: bridge vs pass_through after semantic_route."""
        from neuroswarm_arm.runtime.router.tool_search import (
            BRIDGE_TOOL_SCHEMA,
            ToolSearchConfig,
            build_listing_manifest,
            decide_mode,
        )
        from neuroswarm_arm.runtime.router.tool_schema_builder import estimate_schema_tokens
        from neuroswarm_arm.runtime.router.tool_search.metrics import record_mode, record_truncated

        cfg = ToolSearchConfig.from_env()
        result = ctx.baggage.get("router_result")
        schemas = list(state.get("tool_schemas") or [])
        registry = getattr(semantic_router, "registry", None)
        catalog = list(registry.as_list()) if registry is not None and hasattr(registry, "as_list") else []

        initial_ids: set[str] = set()
        if result is not None:
            for scored in list(getattr(result, "tools", None) or []):
                tool = getattr(scored, "tool", scored)
                tid = getattr(tool, "id", None) or getattr(tool, "name", None)
                if tid:
                    initial_ids.add(str(tid))
        for schema in schemas:
            fn = schema.get("function") if isinstance(schema, dict) else None
            if isinstance(fn, dict) and fn.get("name"):
                initial_ids.add(str(fn["name"]))
            tid = schema.get("id") if isinstance(schema, dict) else None
            if tid:
                initial_ids.add(str(tid))

        deferred = []
        for tool in catalog:
            tid = str(getattr(tool, "id", "") or getattr(tool, "name", "") or "")
            if tid and tid not in initial_ids:
                deferred.append(tool)

        deferred_tokens = 0
        for tool in deferred:
            schema = {
                "name": getattr(tool, "name", ""),
                "description": getattr(tool, "description", ""),
                "parameters": getattr(tool, "input_schema", {}) or {},
            }
            deferred_tokens += estimate_schema_tokens(schema)

        before = int(getattr(result, "prompt_tokens_before", 0) or 0) if result is not None else 0
        ctx_len = max(before, 8192)
        mode = decide_mode(
            enabled=cfg.enabled,
            threshold_pct=cfg.threshold_pct,
            context_length=ctx_len,
            deferred_schema_tokens=deferred_tokens,
            has_deferrable=bool(deferred),
        )
        record_mode(mode)
        state["tool_search_mode"] = mode
        ctx.baggage["tool_search_mode"] = mode
        if mode == "pass_through":
            return mode

        # Bridge: exactly one synthetic schema + listing manifest (no deferrable schemas).
        state["tool_schemas"] = [BRIDGE_TOOL_SCHEMA]
        ctx.baggage["tool_schemas"] = state["tool_schemas"]
        truncated = False
        if cfg.listing in {"auto", "on"}:
            manifest, truncated = build_listing_manifest(catalog or deferred, cfg.listing_max_tokens)
            state["tool_prompt_block"] = manifest
            ctx.baggage["tool_prompt_block"] = manifest
        if truncated:
            record_truncated()
            state["tool_search_listing_truncated"] = True
            ctx.baggage["tool_search_listing_truncated"] = True
        return mode

    def kv_session(ctx: ExecutionContext) -> str:
        session_id = state["session_id"]
        if kv_runtime is None:
            return session_id
        agent_id = getattr(request, "agent_id", "") or ctx.ids.agent_id
        kv_runtime.create_session(session_id, agent_id=agent_id)
        messages = getattr(request, "messages", None) or []
        prompt = getattr(messages[-1], "content", "") if messages else ""
        payload = (prompt or "").encode("utf-8")[:4096]

        async def _persist() -> None:
            await kv_runtime.allocate(session_id, payload, agent_id=agent_id)

        anyio.run(_persist)
        ctx.baggage["session_id"] = session_id
        return session_id

    def okf_tool_docs(ctx: ExecutionContext) -> str:
        tool_names = list(state.get("tool_names") or ctx.baggage.get("tool_names") or [])
        bridge = state.get("tool_search_mode") == "bridge"
        if _acr_enabled():
            from neuroswarm_arm.runtime.acr.connectors import build_context_for_haoe

            agent_id = getattr(request, "agent_id", "") or ctx.ids.agent_id or "default"
            snap = build_context_for_haoe(
                acr,
                query=_query_text() or "nexus overview",
                owner=agent_id,
                agent_role=_agent_profile(),
                tool_names=tool_names,
                tool_prompt_block=state.get("tool_prompt_block") or "",
            )
            if snap is None:
                return ""
            merged = snap.prompt or ""
            state["acr_snapshot"] = snap
            state["okf_merged_context"] = merged
            ctx.baggage["acr_snapshot_version"] = snap.version.version_id
            ctx.baggage["acr_compression_ratio"] = snap.stats.compression.compression_ratio
            ctx.baggage["acr_token_reduction"] = snap.stats.compression.token_reduction
            ctx.baggage["acr_information_retained"] = snap.stats.compression.information_retained
            ctx.baggage["okf_tokens"] = int(snap.stats.output_tokens or 0)
            ctx.baggage["okf_merged_context"] = merged
            ctx.baggage["okf_tool_docs"] = ""
            # Prefer ACR prompt; in bridge mode keep Hermes listing as tool_prompt_block.
            if merged and not bridge:
                state["tool_prompt_block"] = merged
                ctx.baggage["tool_prompt_block"] = merged
            return merged

        if okf_runtime is None:
            return ""
        from nexus_okf.runtime.mem0_bridge import merge_mem0_okf

        docs = okf_runtime.load_tool_docs(tool_names, budget=600)
        merged = merge_mem0_okf(state.get("mem0_facts") or [], state.get("okf_knowledge"), docs)
        state["okf_merged_context"] = merged
        ctx.baggage["okf_tool_docs"] = getattr(docs, "text", "") or ""
        ctx.baggage["okf_merged_context"] = merged
        # Append institutional context to tool prompt block (after routing).
        # Bridge mode keeps listing-only prompt — do not append full OKF dump over it.
        if merged and not bridge:
            existing = state.get("tool_prompt_block") or ""
            state["tool_prompt_block"] = (existing + "\n\n" + merged).strip()
            ctx.baggage["tool_prompt_block"] = state["tool_prompt_block"]
        return merged

    def cascade_node(ctx: ExecutionContext) -> Any:
        session_id = state["session_id"]
        tool_names = state["tool_names"]
        req = request
        if hasattr(request, "model_copy"):
            req = request.model_copy(update={"session_id": session_id})
        handle_kwargs: dict[str, Any] = {
            "tool_schemas": state.get("tool_schemas") or None,
            "tool_confidence": state.get("tool_confidence"),
            "tool_prompt_block": state.get("tool_prompt_block") or None,
        }
        if ctx.baggage.get("router_result") is not None:
            handle_kwargs["router_result"] = ctx.baggage["router_result"]
        if state.get("tool_high_confidence"):
            handle_kwargs["tool_high_confidence"] = True
            budget = state.get("high_conf_thinking_budget")
            if budget is not None:
                handle_kwargs["high_conf_thinking_budget"] = int(budget)
        try:
            response = engine.handle(req, tool_names, **handle_kwargs)
        except TypeError:
            # Cascade / older adapters may not accept high-conf kwargs.
            handle_kwargs.pop("tool_high_confidence", None)
            handle_kwargs.pop("high_conf_thinking_budget", None)
            response = engine.handle(req, tool_names, **handle_kwargs)
        # Surface cost-router decision on response metrics (real values only).
        cost_meta = state.get("cost_router") or {}
        if cost_meta and hasattr(response, "model_copy"):
            metrics = dict(getattr(response, "metrics", None) or {})
            metrics["cost_router_tier"] = cost_meta.get("tier")
            metrics["cost_router_reason"] = cost_meta.get("reason")
            if state.get("schema_token_reduction") is not None:
                metrics["schema_token_reduction"] = state.get("schema_token_reduction")
            try:
                response = response.model_copy(update={"metrics": metrics})
            except Exception:
                pass
        elif cost_meta and isinstance(getattr(response, "metrics", None), dict):
            response.metrics["cost_router_tier"] = cost_meta.get("tier")
            response.metrics["cost_router_reason"] = cost_meta.get("reason")
        state["response"] = response
        ctx.baggage["response"] = response
        # Memory plane can block (json_emergency lock / Mem0). Never stall chat reply.
        try:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
                _fut = _pool.submit(_memory_writeback, ctx, response)
                _fut.result(timeout=2.0)
        except Exception:
            pass
        return response

    def _memory_writeback(ctx: ExecutionContext, response: Any) -> None:
        neuro = _neuro()
        if neuro is None:
            return
        agent_id = getattr(request, "agent_id", "") or ctx.ids.agent_id or "default"
        workflow_id = getattr(ctx.ids, "workflow_id", "") or ""
        execution_id = getattr(ctx.ids, "execution_id", "") or ""
        tool_names = list(state.get("tool_names") or [])
        text = ""
        try:
            text = str(getattr(response, "content", "") or getattr(response, "text", "") or "")
        except Exception:
            text = ""
        latency = float(getattr(response, "latency_ms", 0) or ctx.baggage.get("latency_ms", 0) or 0)
        cost = float(getattr(response, "cost_usd", 0) or ctx.baggage.get("cost_usd", 0) or 0)
        ok = not bool(getattr(response, "error", None))
        try:
            # Official Mem0 loop: ADD conversation messages for extraction
            msgs: list[dict[str, str]] = []
            for m in getattr(request, "messages", None) or []:
                role = str(getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else "user") or "user")
                content = str(
                    getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "") or ""
                )
                if content:
                    msgs.append({"role": role, "content": content})
            if text:
                msgs.append({"role": "assistant", "content": text[:4000]})
            if msgs and hasattr(neuro, "remember"):
                try:
                    neuro.remember(
                        msgs,
                        owner=agent_id,
                        agent_id=agent_id,
                        run_id=execution_id,
                        metadata={"workflow_id": workflow_id, "source": "chat_cascade"},
                    )
                except Exception:
                    pass
            if ok:
                neuro.remember_success(
                    f"chat success tools={','.join(tool_names)}",
                    owner=agent_id,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    latency=latency,
                    cost=cost,
                    success_score=1.0,
                    origin_agent=agent_id,
                    tags=["chat", "success"],
                )
                if text:
                    neuro.remember_execution(
                        text[:2000],
                        owner=agent_id,
                        workflow_id=workflow_id,
                        execution_id=execution_id,
                        origin_agent=agent_id,
                    )
            else:
                reason = str(getattr(response, "error", "unknown"))
                neuro.remember_failure(
                    f"chat failure: {reason}",
                    owner=agent_id,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    failure_reason=reason,
                    origin_agent=agent_id,
                    tags=["chat", "failure"],
                )
            if tool_names:
                for tid in tool_names:
                    neuro.remember_tool(
                        f"routed tool={tid}",
                        owner=agent_id,
                        metadata={"tool_id": tid},
                        workflow_id=workflow_id,
                        origin_agent=agent_id,
                    )
            neuro.remember_workflow(
                f"workflow=chat tools={len(tool_names)} ok={ok}",
                owner=agent_id,
                workflow_id=workflow_id or "chat",
                execution_id=execution_id,
                origin_agent=agent_id,
            )
            if latency > 0:
                neuro.remember_latency(
                    f"chat latency_ms={latency}",
                    owner=agent_id,
                    latency=latency,
                    workflow_id=workflow_id,
                )
            if cost > 0:
                neuro.remember_cost(
                    f"chat cost_usd={cost}",
                    owner=agent_id,
                    cost=cost,
                    workflow_id=workflow_id,
                )
            neuro.reflect(
                owner=agent_id,
                workflow_id=workflow_id or "chat",
                success=ok,
                failures=[] if ok else [str(getattr(response, "error", "failure"))],
                tools_used=tool_names,
                notes=_query_text()[:240],
                latency_ms=latency,
                cost=cost,
                origin_agent=agent_id,
            )
            snap = state.get("acr_snapshot")
            if snap is not None and _acr_enabled():
                try:
                    from neuroswarm_arm.runtime.acr.connectors import record_rtg_outcome

                    record_rtg_outcome(
                        acr,
                        snap,
                        success=ok,
                        cost=cost,
                        latency_ms=latency,
                        owner=agent_id,
                    )
                except Exception:
                    pass
        except Exception:
            # Memory must never break chat path
            pass

    def kv_checkpoint(ctx: ExecutionContext) -> str:
        session_id = state["session_id"]
        if kv_runtime is None:
            return session_id

        async def _ckpt() -> None:
            await kv_runtime.checkpoint(session_id)

        anyio.run(_ckpt)
        return session_id

    def response_node(ctx: ExecutionContext) -> Any:
        return state["response"]

    return {
        "mem0_recall": mem0_recall,
        "okf_context": okf_context,
        "semantic_route": semantic_route,
        "tool_search_activation": tool_search_activation,
        "okf_tool_docs": okf_tool_docs,
        "kv_session": kv_session,
        "cascade": cascade_node,
        "kv_checkpoint": kv_checkpoint,
        "response": response_node,
    }


def correlation_from_request(request: Any) -> CorrelationIds:
    return CorrelationIds(
        request_id=getattr(request, "session_id", None) or uuid4().hex,
        agent_id=getattr(request, "agent_id", "") or "",
        workflow_id=uuid4().hex,
        trace_id=uuid4().hex,
        execution_id=uuid4().hex,
        correlation_id=uuid4().hex,
    )
