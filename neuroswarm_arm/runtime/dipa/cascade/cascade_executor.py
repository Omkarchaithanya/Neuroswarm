"""Single-tier cascade generate via the backend registry."""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol

from ..interfaces.types import GenerateRequest, GenerateResult, InferenceRequest, TokenChunk
from .cascade_policy import TierPolicy

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.armcascade.interfaces.types import Proposal

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

    def _backend(self, tier: TierPolicy) -> Any:
        if hasattr(self.registry, "require"):
            return self.registry.require(tier.backend)
        backend = self.registry.get(tier.backend)
        if backend is None:
            raise KeyError(f"backend not registered: {tier.backend}")
        return backend

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
        backend = self._backend(tier)
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

        if gen_req.speculative and _env_bool("NSA_DRAFT_VERIFY_AFFINITY", True):
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

    async def generate_tier_stream(
        self,
        req: InferenceRequest,
        tier: TierPolicy,
        ctx: ExecutionContext,
        draft: Proposal | Any,
        *,
        quant: str = "",
        top_logprobs: int = 5,
        tau_floor: float = 0.0,
        max_tokens: int | None = None,
        kv_handle: str | None = None,
    ) -> AsyncIterator[TokenChunk]:
        """Stream Leviathan accepts as target logprobs arrive."""
        backend = self._backend(tier)
        if _env_bool("NSA_DRAFT_VERIFY_AFFINITY", True):
            self._apply_spec_affinity(tier, ctx)

        messages = build_messages(req)
        draft_len = int(
            getattr(draft, "draft_len", 0)
            or approx_tokens(str(getattr(draft, "text", "") or ""))
            or 1
        )
        n_tokens = int(max_tokens if max_tokens is not None else draft_len + 1)
        quant_s = quant or getattr(ctx, "quant", "") or ""
        handle = kv_handle if kv_handle is not None else getattr(ctx, "kv_handle", None)
        id_slot = getattr(ctx, "id_slot", None)

        if hasattr(backend, "generate_with_logits_stream"):
            async for chunk in backend.generate_with_logits_stream(
                messages,
                max_tokens=n_tokens,
                temperature=float(req.temperature),
                top_logprobs=int(top_logprobs),
                session_id=req.session_id,
                quant=quant_s,
                kv_handle=handle,
                id_slot=id_slot,
                ctx=ctx,
                draft=draft,
                tau_floor=tau_floor,
            ):
                yield chunk
            return

        # Fallback: block logits then emit accepted prefix (+ bonus) as chunks.
        from neuroswarm_arm.runtime.armcascade.verification.logits_verifier import (
            leviathan_accept,
            parse_logits_bundle,
        )

        if not hasattr(backend, "generate_with_logits"):
            text = str(getattr(draft, "text", "") or "")
            if text:
                yield TokenChunk(text=text, index=0, finished=False)
            yield TokenChunk(text="", index=1, finished=True)
            return

        result = await backend.generate_with_logits(
            messages,
            max_tokens=n_tokens,
            temperature=float(req.temperature),
            top_logprobs=int(top_logprobs),
            session_id=req.session_id,
            quant=quant_s,
            kv_handle=handle,
            id_slot=id_slot,
            ctx=ctx,
        )
        raw = dict(result.raw) if result.raw else {}
        bundle = parse_logits_bundle(
            raw,
            draft,
            completion_text=result.text or "",
            top_n=int(top_logprobs),
        )
        accept = leviathan_accept(
            bundle,
            greedy=float(req.temperature) == 0.0,
            tau_floor=tau_floor,
        )
        words = list(bundle.draft_tokens)
        index = 0
        for i in range(accept.accepted_prefix_len):
            tok = words[i] if i < len(words) else ""
            if tok:
                yield TokenChunk(
                    text=tok,
                    index=index,
                    finished=False,
                    metrics={
                        "accepted_prefix_len": float(i + 1),
                        "logits_available": 1.0,
                    },
                )
                index += 1
        if accept.bonus_token:
            yield TokenChunk(
                text=accept.bonus_token,
                index=index,
                finished=False,
                metrics={
                    "accepted_prefix_len": float(accept.accepted_prefix_len),
                    "bonus": 1.0,
                },
            )
            index += 1
        yield TokenChunk(
            text="",
            index=index,
            finished=True,
            metrics={"accepted_prefix_len": float(accept.accepted_prefix_len)},
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
