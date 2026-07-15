"""Protocols / interfaces for Task Graph extension points."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from .enums import NodeStatus


@runtime_checkable
class ICondition(Protocol):
    """Evaluable, composable execution condition."""

    kind: Any

    def evaluate(self, ctx: Mapping[str, Any]) -> bool: ...

    def to_dict(self) -> dict[str, Any]: ...


@runtime_checkable
class INodeHandler(Protocol):
    """Injected node body. Swarm executor never owns agent/DIPA logic."""

    async def __call__(
        self,
        node_id: str,
        context: Mapping[str, Any],
    ) -> Any: ...


@runtime_checkable
class IEventSink(Protocol):
    """Receive Task Graph lifecycle events (OTel-ready)."""

    def emit(self, event: Any) -> None: ...


@runtime_checkable
class IMetricsSink(Protocol):
    """Receive metric updates without binding to Prometheus."""

    def record(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None: ...


@runtime_checkable
class ISerializer(Protocol):
    def dumps(self, graph: Any, *, fmt: Any = None) -> bytes: ...

    def loads(self, data: bytes, *, fmt: Any = None) -> Any: ...


@runtime_checkable
class IValidator(Protocol):
    def validate(self, graph: Any) -> Any: ...


@runtime_checkable
class ICancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...

    def cancel(self, *, forced: bool = False) -> None: ...

    def throw_if_cancelled(self) -> None: ...


@runtime_checkable
class IExecutionEngine(Protocol):
    async def run(self, graph: Any, handlers: Mapping[str, INodeHandler]) -> Any: ...

    def cancel(self, mode: Any, *, node_id: str | None = None, forced: bool = False) -> None: ...


def status_is_success(status: NodeStatus) -> bool:
    from .enums import SUCCESS_STATUSES

    return status in SUCCESS_STATUSES
