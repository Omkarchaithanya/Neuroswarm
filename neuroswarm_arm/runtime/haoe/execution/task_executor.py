"""Task executor — runs one TaskNode under an ExecutionContext."""

from __future__ import annotations

from time import monotonic
from typing import Any

from ..core.task_graph import TaskNode
from ..interfaces.types import ExecutorKind, TaskState
from ..workflow.cancellation import CancelledError
from ..workflow.retry_manager import RetryManager
from .async_executor import (
    AsyncExecutor,
    InlineExecutor,
    NativeExecutorStub,
    ProcessExecutor,
    ThreadExecutor,
    select_executor,
)
from .execution_context import (
    ExecutionContext,
    reset_current_context,
    set_current_context,
)


class TaskExecutor:
    def __init__(
        self,
        *,
        thread_workers: int = 8,
        process_workers: int = 0,
        retry_manager: RetryManager | None = None,
    ) -> None:
        self.inline = InlineExecutor()
        self.thread = ThreadExecutor(max_workers=thread_workers)
        self.process = (
            ProcessExecutor(max_workers=process_workers) if process_workers > 0 else None
        )
        self.async_ex = AsyncExecutor()
        self.native = NativeExecutorStub()
        self.retry = retry_manager or RetryManager()

    def execute(self, node: TaskNode, ctx: ExecutionContext) -> Any:
        if node.fn is None:
            if node.sm.state is TaskState.QUEUED:
                node.sm.transition(TaskState.READY)
            if node.sm.state is TaskState.READY:
                node.sm.transition(TaskState.RUNNING)
            node.sm.force(TaskState.COMPLETED)
            node.result = None
            return None

        ctx.cancellation.throw_if_cancelled()
        if node.sm.state is TaskState.QUEUED:
            node.sm.transition(TaskState.READY)
        if node.sm.state is TaskState.READY:
            node.sm.transition(TaskState.RUNNING)
        elif node.sm.state is not TaskState.RUNNING:
            node.sm.force(TaskState.RUNNING)

        token = set_current_context(ctx)
        start = monotonic()
        try:

            def _on_retry(_attempt: int, _exc: BaseException) -> None:
                node.attempts += 1
                if node.sm.state is TaskState.RUNNING:
                    node.sm.transition(TaskState.RETRY)
                else:
                    node.sm.force(TaskState.RETRY)
                node.sm.force(TaskState.RUNNING)

            def _call() -> Any:
                ctx.cancellation.throw_if_cancelled()
                assert node.fn is not None
                return node.fn(ctx)

            result = self.retry.run(
                _call,
                policy=node.retry,
                token=ctx.cancellation,
                on_retry=_on_retry,
            )
            node.sm.force(TaskState.COMPLETED)
            node.result = result
            node.attempts += 1
            return result
        except CancelledError as exc:
            node.error = exc
            node.sm.force(TaskState.CANCELLED)
            raise
        except Exception as exc:
            node.error = exc
            node.sm.force(TaskState.FAILED)
            raise
        finally:
            reset_current_context(token)
            node.metadata["runtime_ms"] = (monotonic() - start) * 1000.0

    def run_callable(self, kind: ExecutorKind, fn: Any, *args: Any, **kwargs: Any) -> Any:
        ex = select_executor(
            kind,
            thread=self.thread,
            process=self.process,
            async_ex=self.async_ex,
            inline=self.inline,
            native=self.native,
        )
        return ex.run(fn, *args, **kwargs)

    def shutdown(self) -> None:
        self.thread.shutdown(wait=False)
        if self.process is not None:
            self.process.shutdown(wait=False)
        self.async_ex.shutdown()
        self.native.shutdown()
        self.inline.shutdown()
