"""Concrete executors — async, thread, process, inline."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, Future
from typing import Any, Callable

from ..interfaces import IExecutor, INativeExecutor
from ..interfaces.types import ExecutorKind


class InlineExecutor(IExecutor):
    kind = ExecutorKind.INLINE

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    def shutdown(self, wait: bool = True) -> None:
        return None


class ThreadExecutor(IExecutor):
    kind = ExecutorKind.THREAD

    def __init__(self, max_workers: int = 8) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="haoe-thr")

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        fut = self._pool.submit(fn, *args, **kwargs)
        return fut.result()

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        return self._pool.submit(fn, *args, **kwargs)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=not wait)


class ProcessExecutor(IExecutor):
    kind = ExecutorKind.PROCESS

    def __init__(self, max_workers: int = 2) -> None:
        self._max = max(1, max_workers)
        self._pool: ProcessPoolExecutor | None = None

    def _ensure(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=self._max)
        return self._pool

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        # Process pool requires picklable top-level callables; callers must comply.
        fut = self._ensure().submit(fn, *args, **kwargs)
        return fut.result()

    def shutdown(self, wait: bool = True) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=wait, cancel_futures=not wait)
            self._pool = None


class AsyncExecutor(IExecutor):
    """Run sync callables in a thread via asyncio, or await coroutines."""

    kind = ExecutorKind.ASYNC

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(result)
            # Already in async context — schedule and wait via nest-free path.
            # Prefer caller to use awaitable API; for sync bridge use new thread loop.
            return asyncio.run_coroutine_threadsafe(result, loop).result()
        return result

    async def run_async(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return await asyncio.to_thread(lambda: result)

    def shutdown(self, wait: bool = True) -> None:
        return None


class NativeExecutorStub(INativeExecutor):
    """Future Rust/C scheduler — falls back to inline today."""

    kind = ExecutorKind.NATIVE

    def __init__(self) -> None:
        self._fallback = InlineExecutor()

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return self._fallback.run(fn, *args, **kwargs)

    def shutdown(self, wait: bool = True) -> None:
        self._fallback.shutdown(wait=wait)


def select_executor(
    kind: ExecutorKind,
    *,
    thread: ThreadExecutor,
    process: ProcessExecutor | None,
    async_ex: AsyncExecutor,
    inline: InlineExecutor,
    native: NativeExecutorStub,
) -> IExecutor:
    if kind is ExecutorKind.THREAD:
        return thread
    if kind is ExecutorKind.PROCESS:
        return process or inline
    if kind is ExecutorKind.ASYNC:
        return async_ex
    if kind is ExecutorKind.NATIVE:
        return native
    return inline
