"""Recovery stack facade — fallbacks then degraded mode."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..interfaces.types import (
    GenerateRequest,
    InferenceRequest,
    InferenceResponse,
)
from .circuit_breaker import CircuitBreaker
from .degraded_mode import DegradedMode
from .fallback_manager import FallbackKind, FallbackManager
from .retry_manager import RetryManager
from .timeout_manager import TimeoutManager

if TYPE_CHECKING:
    from ..execution.execution_context import ExecutionContext
    from ..interfaces.backend import InferenceBackend


class SupportsBackendLookup(Protocol):
    def get(self, name: str) -> InferenceBackend: ...


class RecoveryStack:
    """Pipeline recovery boundary used as ``runtime.recovery``.

    ``handle_failure`` walks plan fallbacks (respecting the circuit breaker),
    then returns a degraded response when nothing else works.
    """

    def __init__(
        self,
        *,
        registry: SupportsBackendLookup | None = None,
        retry: RetryManager | None = None,
        timeout: TimeoutManager | None = None,
        circuit: CircuitBreaker | None = None,
        fallbacks: FallbackManager | None = None,
        degraded: DegradedMode | None = None,
        telemetry: object | None = None,
    ) -> None:
        self.registry = registry
        self.retry = retry or RetryManager()
        self.timeout = timeout or TimeoutManager()
        self.circuit = circuit or CircuitBreaker()
        self.fallbacks = fallbacks or FallbackManager()
        self.degraded = degraded or DegradedMode()
        self.telemetry = telemetry

    def _telem(self, method: str) -> None:
        t = self.telemetry
        if t is None:
            return
        fn = getattr(t, method, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def handle_failure(
        self,
        req: InferenceRequest,
        ctx: ExecutionContext,
        exc: BaseException,
    ) -> InferenceResponse | None:
        """Attempt fallback backends then degraded mode.

        Returns ``None`` only when no recovery policy applies (caller re-raises).
        """
        plan = ctx.plan
        if plan is None and self.registry is None:
            return self.degraded.respond(req)

        # Record failure against the backend that was selected.
        failed_backend = ctx.backend_name or (plan.backend if plan else "")
        if failed_backend:
            self.circuit.record_failure(failed_backend)
        self._telem("record_retry")

        if self.registry is not None and plan is not None:
            recovered = self._try_fallbacks(req, ctx, exc)
            if recovered is not None:
                return recovered

        return self.degraded.respond(req)

    def _try_fallbacks(
        self,
        req: InferenceRequest,
        ctx: ExecutionContext,
        exc: BaseException,
    ) -> InferenceResponse | None:
        assert self.registry is not None
        plan = ctx.plan
        assert plan is not None

        targets = self.fallbacks.targets(plan)
        if not targets:
            return None

        model = plan.model
        quant = plan.quant
        last_exc: BaseException = exc

        for target in targets:
            if target.kind == FallbackKind.MODEL:
                model = target.value
                continue
            if target.kind == FallbackKind.QUANT:
                quant = target.value
                continue
            # BACKEND
            backend_name = target.value
            if not self.circuit.allow(backend_name):
                continue
            backend = self.registry.get(backend_name)
            if backend is None:
                self.circuit.record_failure(backend_name)
                continue

            for attempt in range(self.retry.max_retries + 1):
                try:
                    result = self._generate_sync(
                        backend,
                        req,
                        ctx,
                        quant=quant,
                    )
                    self.circuit.record_success(backend_name)
                    return InferenceResponse(
                        text=result.text,
                        model=model or result.model or req.model,
                        tier_used=result.tier_used or 0,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        thinking_token_cap=req.thinking_token_cap or 0,
                        tool_schemas_used=list(req.tool_names),
                        quant=quant or result.quant,
                        backend=result.backend or backend_name,
                        plan=plan,
                        metrics={
                            "recovered": 1.0,
                            "fallback": 1.0,
                            "latency_ms": float(result.latency_ms),
                        },
                        degraded=False,
                    )
                except Exception as attempt_exc:  # noqa: BLE001 — recovery loop
                    last_exc = attempt_exc
                    self.circuit.record_failure(backend_name)
                    if not self.retry.should_retry(attempt_exc, attempt):
                        break

        _ = last_exc
        return None

    def _generate_sync(
        self,
        backend: InferenceBackend,
        req: InferenceRequest,
        ctx: ExecutionContext,
        *,
        quant: str,
    ):
        import asyncio

        messages = [dict(m) for m in req.messages]
        if req.system_prompt:
            messages = [{"role": "system", "content": req.system_prompt}] + messages
        gen_req = GenerateRequest(
            messages=messages,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            session_id=req.session_id,
            quant=quant,
            stream=False,
            kv_handle=ctx.kv_handle,
        )

        async def _run():
            return await self.timeout.run(backend.generate(gen_req, ctx))

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # Nested event loop — run in a fresh loop via thread if needed.
            # Callers (pipeline) typically invoke recovery from sync context.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run, _run())
                return fut.result()
        return asyncio.run(_run())


# Alias for factory / docs that prefer the RecoveryManager name.
RecoveryManager = RecoveryStack
