"""OpenTelemetry integration — uses global provider owned by ARMORA ROF.

Does NOT call set_tracer_provider. When ROF has bootstrapped the SDK provider,
this adapter attaches spans; otherwise it is a no-op.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from ..interfaces.types import CorrelationIds


class OpenTelemetryAdapter:
    def __init__(self, *, enabled: bool = False, endpoint: str = "") -> None:
        # endpoint kept for config compat; provider ownership is ROF
        self.enabled = bool(enabled)
        self.endpoint = endpoint
        self._tracer = None
        if self.enabled:
            self._try_init()

    def _try_init(self) -> None:
        try:
            from opentelemetry import trace

            # Use whatever TracerProvider ROF (or host) already configured.
            self._tracer = trace.get_tracer("haoe")
        except Exception:
            self.enabled = False
            self._tracer = None

    @contextmanager
    def span(
        self,
        name: str,
        ids: CorrelationIds | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        if not self.enabled or self._tracer is None:
            yield None
            return
        attrs = dict(attributes or {})
        if ids is not None:
            attrs.update(ids.to_dict())
        with self._tracer.start_as_current_span(name, attributes=attrs) as span:
            yield span
