"""ARMORA client — thin DX proxy over IInferenceEngine."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.interfaces.engine import IInferenceEngine

from .budget import ArmoraBudgetPolicy, BudgetConfig


class ArmoraClient:
    """Drop-in facade: load_model / generate / stream / warmup / metrics / health / shutdown."""

    def __init__(
        self,
        engine: IInferenceEngine,
        *,
        budget: ArmoraBudgetPolicy | None = None,
    ) -> None:
        self.engine = engine
        self.budget = budget or ArmoraBudgetPolicy()

    def load_model(
        self, model_ref: str, *, options: Mapping[str, Any] | None = None
    ) -> str:
        return self.engine.load_model(model_ref, options=options)

    def require_envelope(self, envelope_id: str | None = None) -> str:
        """Refuse inference without a frozen envelope binding."""
        eid = envelope_id or getattr(self.budget, "_session_envelope_id", None)
        if not eid:
            # Lazily ensure session envelope via compat adapter
            if hasattr(self.budget, "_ensure_session"):
                eid = self.budget._ensure_session()
            else:
                raise RuntimeError("ARMORA requires a frozen BudgetEnvelope")
        if hasattr(self.budget, "bind_request_envelope"):
            self.budget.bind_request_envelope(str(eid))
        return str(eid)

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "cascade",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        session_id: str = "",
        cost_usd: float = 0.0,
        envelope_id: str | None = None,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        self.require_envelope(envelope_id)
        if cost_usd and not self.budget.charge(cost_usd):
            raise RuntimeError("ARMORA budget exceeded")
        return self.engine.generate(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            session_id=session_id,
            **kwargs,
        )

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
        return self.engine.stream(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            session_id=session_id,
            **kwargs,
        )

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
        async for chunk in self.engine.astream(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            session_id=session_id,
            **kwargs,
        ):
            yield chunk

    def warmup(self, *, model: str | None = None) -> Mapping[str, Any]:
        return self.engine.warmup(model=model)

    def metrics(self) -> Mapping[str, Any]:
        out = dict(self.engine.metrics())
        out["budget"] = self.budget.status()
        return out

    def health(self) -> Mapping[str, Any]:
        return self.engine.health()

    def shutdown(self) -> None:
        self.engine.shutdown()


def build_armora(
    engine: IInferenceEngine,
    *,
    budget: BudgetConfig | ArmoraBudgetPolicy | None = None,
) -> ArmoraClient:
    if isinstance(budget, BudgetConfig):
        policy = ArmoraBudgetPolicy(budget)
    elif isinstance(budget, ArmoraBudgetPolicy):
        policy = budget
    else:
        policy = ArmoraBudgetPolicy()
    return ArmoraClient(engine, budget=policy)
