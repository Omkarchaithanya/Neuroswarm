"""Execution context — correlation, cancel, retry, baggage propagation."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from ..interfaces.types import CorrelationIds, RetryPolicy
from ..workflow.cancellation import CancellationToken


@dataclass
class ExecutionContext:
    ids: CorrelationIds = field(default_factory=CorrelationIds)
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_s: float | None = None
    baggage: dict[str, Any] = field(default_factory=dict)
    pool_hint: str = ""
    numa_node: int | None = None

    def child(self, *, agent_id: str | None = None) -> ExecutionContext:
        return ExecutionContext(
            ids=self.ids.child(agent_id=agent_id),
            cancellation=self.cancellation.child(),
            retry=self.retry,
            timeout_s=self.timeout_s,
            baggage=dict(self.baggage),
            pool_hint=self.pool_hint,
            numa_node=self.numa_node,
        )


_CURRENT: ContextVar[ExecutionContext | None] = ContextVar("haoe_execution_context", default=None)


def get_current_context() -> ExecutionContext | None:
    return _CURRENT.get()


def set_current_context(ctx: ExecutionContext | None):
    return _CURRENT.set(ctx)


def reset_current_context(token: Any) -> None:
    _CURRENT.reset(token)
