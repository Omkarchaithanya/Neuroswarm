"""Retry manager — applies RetryPolicy with backoff."""

from __future__ import annotations

from time import sleep
from typing import Any, Callable

from ..interfaces.types import RetryPolicy
from .cancellation import CancellationToken, CancelledError


class RetryManager:
    def __init__(self, default_policy: RetryPolicy | None = None) -> None:
        self._default = default_policy or RetryPolicy()
        self.retry_count = 0

    def run(
        self,
        fn: Callable[[], Any],
        *,
        policy: RetryPolicy | None = None,
        token: CancellationToken | None = None,
        on_retry: Callable[[int, BaseException], None] | None = None,
    ) -> Any:
        pol = policy or self._default
        attempt = 0
        while True:
            if token is not None:
                token.throw_if_cancelled()
            try:
                return fn()
            except CancelledError:
                raise
            except pol.retryable_exceptions as exc:
                attempt += 1
                if attempt >= pol.max_attempts:
                    raise
                self.retry_count += 1
                if on_retry is not None:
                    on_retry(attempt, exc)
                delay = pol.delay_for(attempt - 1)
                if token is not None:
                    if token.wait(delay):
                        raise CancelledError("cancelled during retry backoff")
                else:
                    sleep(delay)
