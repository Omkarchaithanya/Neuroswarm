"""DIPA adapter — stage spans for planner / routing / infer / stream."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from ..instrumentation import instrument_infer, instrument_planner, instrument_routing, instrument_streaming
from ..schemas import EventType, SpanNames
from ..spans import decision_attributes


class DIPAObservabilityAdapter:
    """Injected into DIPA pipeline without DIPA owning OTel providers."""

    def __init__(self, rof: Any) -> None:
        self.rof = rof

    def planner(self, **attrs: Any) -> Any:
        return instrument_planner(self.rof, **attrs)

    def routing(self, **attrs: Any) -> Any:
        return instrument_routing(self.rof, **attrs)

    def infer(self, **attrs: Any) -> Any:
        return instrument_infer(self.rof, **attrs)

    def streaming(self, **attrs: Any) -> Any:
        return instrument_streaming(self.rof, **attrs)

    @contextmanager
    def backend(self, backend_id: str, **attrs: Any) -> Iterator[Any]:
        attributes = decision_attributes(backend=backend_id, **attrs)
        try:
            with self.rof.span(SpanNames.BACKEND, attributes=attributes) as span:
                yield span
        except Exception as exc:
            self.rof.emit_builtin(
                EventType.BACKEND_FAILURE,
                payload={"backend": backend_id, "error": str(exc)[:256]},
            )
            raise

    @contextmanager
    def quant(self, quantization: str, **attrs: Any) -> Iterator[Any]:
        with self.rof.span(
            SpanNames.QUANT,
            attributes=decision_attributes(quant=quantization, **attrs),
        ) as span:
            yield span

    @contextmanager
    def warm(self, **attrs: Any) -> Iterator[Any]:
        with self.rof.span(SpanNames.WARM, attributes=attrs) as span:
            yield span

    @contextmanager
    def kv(self, **attrs: Any) -> Iterator[Any]:
        with self.rof.span(SpanNames.KV, attributes=attrs) as span:
            yield span

    def record_tokens(
        self,
        *,
        prompt: int = 0,
        completion: int = 0,
        reasoning: int = 0,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if prompt:
            self.rof.counter("nexus_prompt_tokens", float(prompt), labels=labels)
        if completion:
            self.rof.counter("nexus_completion_tokens", float(completion), labels=labels)
        if reasoning:
            self.rof.counter("nexus_reasoning_tokens", float(reasoning), labels=labels)

    def record_backend_selected(self, backend: str, model_tier: str = "") -> None:
        labels = {"backend": backend}
        if model_tier:
            labels["model_tier"] = model_tier
        self.rof.counter("nexus_backend_selected_total", 1.0, labels=labels)
