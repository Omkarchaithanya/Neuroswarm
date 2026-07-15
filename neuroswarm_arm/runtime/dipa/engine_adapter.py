"""InferenceEngineAdapter — DIPARuntime as IInferenceEngine for ARMORA."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.interfaces.engine import IInferenceEngine
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest


class InferenceEngineAdapter(IInferenceEngine):
    """Adapts DIPARuntime (+ control plane) to the frozen ARMORA API."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def load_model(self, model_ref: str, *, options: Mapping[str, Any] | None = None) -> str:
        mm = getattr(self.runtime, "model_manager", None)
        telem = getattr(self.runtime, "telemetry", None)
        opts = dict(options or {})
        backend = str(opts.pop("backend", "") or "")
        quant = str(opts.pop("quant", "") or "")
        if mm is None:
            handle = f"passthrough:{model_ref}"
        else:
            handle = mm.load(model_ref, backend=backend, quant=quant, options=opts)
        if telem is not None:
            telem.record_model_load(model_ref, ok=True)
            with telem.span("inference.model_load", model_ref=model_ref, handle=handle):
                pass
        return handle

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "cascade",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        session_id: str = "",
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        telem = getattr(self.runtime, "telemetry", None)
        req = InferenceRequest(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            session_id=session_id,
            agent_role=str(kwargs.get("agent_role", "tool_call")),
            stream=False,
            baggage=dict(kwargs),
        )
        with self._span(telem, "inference.request", model=model, session_id=session_id):
            result = self.runtime.infer(req)
        if telem is not None:
            telem.record_request(backend=result.metrics.get("backend", ""), status="ok")
            telem.record_token(result.completion_tokens)
        return {
            "text": result.text,
            "model": result.model or model,
            "tier_used": result.tier_used,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "metrics": dict(result.metrics),
            "tool_schemas_used": list(result.tool_schemas_used),
        }

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "cascade",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        session_id: str = "",
        **kwargs: Any,
    ) -> Iterator[Mapping[str, Any]]:
        decode_mgr = getattr(self.runtime, "decode_manager", None)
        prefill_mgr = getattr(self.runtime, "prefill_manager", None)
        kv_xfer = getattr(self.runtime, "kv_transfer", None)
        chunk_planner = getattr(self.runtime, "chunk_planner", None)
        chunk_executor = getattr(self.runtime, "chunk_executor", None)
        cfg = getattr(self.runtime, "config", None)
        pd_mode = str(getattr(cfg, "pd_mode", "off") or "off")
        if (
            pd_mode in {"soft", "native"}
            and decode_mgr is not None
            and prefill_mgr is not None
            and kv_xfer is not None
            and chunk_planner is not None
            and chunk_executor is not None
        ):
            yield from self._stream_pd(
                messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                session_id=session_id,
                **kwargs,
            )
            return
        # Fused path: generate then normalize chunks via streaming engine.
        result = self.generate(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            session_id=session_id,
            **kwargs,
        )
        engine = getattr(self.runtime, "streaming_engine", None)
        if engine is None:
            yield {"text": result.get("text", ""), "index": 0, "finished": True}
            return
        yield from engine.from_text(str(result.get("text", "")), request_id=session_id)

    def _stream_pd(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        max_tokens: int,
        temperature: float,
        session_id: str,
        **kwargs: Any,
    ) -> Iterator[Mapping[str, Any]]:
        from neuroswarm_arm.runtime.dipa.execution.execution_context import (
            ExecutionContext,
        )
        from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest

        req = InferenceRequest(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            session_id=session_id,
            stream=True,
            agent_role=str(kwargs.get("agent_role", "tool_call")),
            baggage=dict(kwargs),
        )
        plan = self.runtime.decision_engine.decide(req)
        ctx = ExecutionContext(request=req, ids=req.ids)
        ctx.plan = plan
        chunk_size = int(getattr(self.runtime.config, "chunk_size", 2048) or 2048)
        chunks = self.runtime.chunk_planner.plan(req, chunk_size=chunk_size)
        results = self.runtime._run_async(
            self.runtime.chunk_executor.run(
                chunks,
                ctx=ctx,
                session_id=session_id,
                quant=plan.quant,
                transfer_mode=plan.transfer_mode,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        )
        handle = self.runtime._run_async(
            self.runtime.kv_transfer.handoff(
                results,
                messages=messages,
                decode_backend=plan.decode_backend or "llama_cpp",
                session_id=session_id,
                quant=plan.quant,
            )
        )
        if plan.model and self.runtime.backends.get(plan.model) is not None:
            handle.decode_backend = plan.model

        async def _collect():
            out = []
            async for chunk in self.runtime.decode_manager.stream_from_handle(
                handle,
                max_tokens=max_tokens,
                temperature=temperature,
                ctx=ctx,
            ):
                out.append(chunk)
            return out

        for chunk in self.runtime._run_async(_collect()):
            yield {
                "text": chunk.text,
                "index": chunk.index,
                "finished": chunk.finished,
                "token_id": chunk.token_id,
            }

    async def astream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "cascade",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        session_id: str = "",
        **kwargs: Any,
    ) -> AsyncIterator[Mapping[str, Any]]:
        for chunk in self.stream(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            session_id=session_id,
            **kwargs,
        ):
            yield chunk
            await asyncio.sleep(0)

    def warmup(self, *, model: str | None = None) -> Mapping[str, Any]:
        wm = getattr(self.runtime, "warmup_manager", None)
        telem = getattr(self.runtime, "telemetry", None)
        with self._span(telem, "inference.warmup", model=model or ""):
            if wm is None:
                out: Mapping[str, Any] = {"ok": True, "skipped": True}
            else:
                out = wm.warmup(model=model)
        if telem is not None:
            telem.record_warmup(ok=True)
        return out

    def warmup_prefix(self, prefix_text: str, *, session_id: str = "") -> Mapping[str, Any]:
        wm = getattr(self.runtime, "warmup_manager", None)
        if wm is None:
            return {"ok": False, "skipped": True}
        return wm.warmup_prefix(prefix_text, session_id=session_id)

    def metrics(self) -> Mapping[str, Any]:
        mc = getattr(self.runtime, "metrics_collector", None)
        status = dict(self.runtime.status())
        if mc is not None:
            status["control"] = mc.snapshot()
        telem = getattr(self.runtime, "telemetry", None)
        if telem is not None:
            status["telemetry"] = telem.snapshot()
        return status

    def health(self) -> Mapping[str, Any]:
        hs = getattr(self.runtime, "health_service", None)
        if hs is not None:
            return hs.health()
        return self.runtime.health()

    def shutdown(self) -> None:
        lm = getattr(self.runtime, "lifecycle_manager", None)
        if lm is not None:
            lm.stop()
        self.runtime.shutdown()

    @staticmethod
    def _span(telem: Any, name: str, **attrs: Any):
        if telem is None:
            from contextlib import nullcontext

            return nullcontext()
        return telem.span(name, **attrs)
