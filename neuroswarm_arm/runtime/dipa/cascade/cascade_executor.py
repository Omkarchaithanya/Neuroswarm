"""Single-tier cascade generate via the backend registry."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, Protocol

from ..interfaces.types import GenerateRequest, GenerateResult, InferenceRequest
from .cascade_policy import TierPolicy

if TYPE_CHECKING:
    from ..execution.execution_context import ExecutionContext
    from ..interfaces.backend import InferenceBackend


class SupportsBackendLookup(Protocol):
    def get(self, name: str, default: InferenceBackend | None = None) -> InferenceBackend | None: ...

    def require(self, name: str) -> InferenceBackend: ...


def approx_tokens(text: str) -> int:
    """Approximate token count by whitespace word split."""
    if not text.strip():
        return 0
    return max(1, len(text.split()))


def build_messages(req: InferenceRequest) -> list[dict[str, str]]:
    """Copy request messages, prepending ``system_prompt`` when set."""
    messages = [dict(m) for m in req.messages]
    if req.system_prompt:
        messages = [{"role": "system", "content": req.system_prompt}] + messages
    return messages


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _pin_cores(cores: list[int]) -> bool:
    if not cores:
        return False
    try:
        from neuroswarm_arm.runtime.armcascade.arm.adapters import _apply_affinity

        return bool(_apply_affinity(set(int(c) for c in cores)))
    except Exception:  # noqa: BLE001
        try:
            if not hasattr(os, "sched_setaffinity"):
                return False
            os.sched_setaffinity(0, set(int(c) for c in cores))
            return True
        except (OSError, AttributeError, PermissionError):
            return False


class CascadeExecutor:
    """Run one cascade tier against a registered :class:`InferenceBackend`."""

    def __init__(self, registry: SupportsBackendLookup) -> None:
        self.registry = registry
        self._affinity_router = None

    def _router(self) -> Any:
        if self._affinity_router is None:
            try:
                from neuroswarm_arm.runtime.dipa.routing.cpu_affinity_router import (
                    CpuAffinityRouter,
                )

                self._affinity_router = CpuAffinityRouter()
            except Exception:  # noqa: BLE001
                self._affinity_router = False
        return self._affinity_router if self._affinity_router is not False else None

    async def generate_tier(
        self,
        req: InferenceRequest,
        tier: TierPolicy,
        ctx: ExecutionContext,
        *,
        quant: str = "",
        speculative: bool = False,
        kv_handle: str | None = None,
        max_tokens: int | None = None,
    ) -> GenerateResult:
        if hasattr(self.registry, "require"):
            backend = self.registry.require(tier.backend)
        else:
            backend = self.registry.get(tier.backend)
            if backend is None:
                raise KeyError(f"backend not registered: {tier.backend}")
        messages = build_messages(req)
        gen_req = GenerateRequest(
            messages=messages,
            max_tokens=int(max_tokens if max_tokens is not None else req.max_tokens),
            temperature=float(req.temperature),
            session_id=req.session_id,
            quant=quant or getattr(ctx, "quant", "") or "",
            stream=False,
            kv_handle=kv_handle if kv_handle is not None else getattr(ctx, "kv_handle", None),
            speculative=speculative,
        )

        if (
            gen_req.speculative
            and _env_bool("NSA_DRAFT_VERIFY_AFFINITY", True)
        ):
            self._apply_spec_affinity(tier, ctx)

        t0 = time.monotonic()
        result = await backend.generate(gen_req, ctx)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        text = result.text
        prompt_tokens = result.prompt_tokens or approx_tokens(
            " ".join(str(m.get("content", "")) for m in messages)
        )
        completion_tokens = result.completion_tokens or approx_tokens(text)

        return GenerateResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=result.latency_ms or elapsed_ms,
            ttft_ms=result.ttft_ms,
            backend=result.backend or tier.backend,
            model=result.model or tier.model,
            quant=result.quant or gen_req.quant,
            tier_used=tier.id,
            raw=dict(result.raw),
            metrics=dict(result.metrics),
        )

    def _apply_spec_affinity(self, tier: TierPolicy, ctx: ExecutionContext) -> bool:
        """Pin draft (tier1) vs verify (tier2+) cores when speculative."""
        plan = getattr(ctx, "plan", None)
        router = self._router()
        phase = "draft" if int(getattr(tier, "id", 1) or 1) <= 1 else "verify"
        cores: list[int] = []
        if phase == "draft":
            cores = list(getattr(ctx, "affinity_draft", None) or [])
            if not cores and router is not None and plan is not None:
                cores = list(router.recommend("draft", plan))
                ctx.affinity_draft = list(cores)
        else:
            cores = list(getattr(ctx, "affinity_verify", None) or [])
            if not cores and router is not None and plan is not None:
                cores = list(router.recommend("verify", plan))
                ctx.affinity_verify = list(cores)
        return _pin_cores(cores)
