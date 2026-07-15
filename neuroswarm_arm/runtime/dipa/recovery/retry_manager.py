"""Retry policy for transient inference failures."""

from __future__ import annotations

from dataclasses import dataclass, field


# Exceptions treated as retryable by default.
_DEFAULT_RETRYABLE: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    OSError,
    RuntimeError,
)


@dataclass
class RetryManager:
    """Decide whether another attempt should be made after a failure."""

    max_retries: int = 2
    retryable: tuple[type[BaseException], ...] = field(
        default_factory=lambda: _DEFAULT_RETRYABLE
    )

    def should_retry(self, exc: BaseException, attempt: int) -> bool:
        """Return ``True`` when *attempt* (0-based) may be retried for *exc*.

        ``attempt`` is the failed attempt index (0 = first failure). Retries
        are allowed while ``attempt < max_retries`` and *exc* is retryable.
        """
        if attempt < 0:
            return False
        if attempt >= self.max_retries:
            return False
        if isinstance(exc, self.retryable):
            return True
        # asyncio.TimeoutError aliases TimeoutError on 3.11+, but keep name check
        name = type(exc).__name__
        if name in {"TimeoutError", "CancelledError"}:
            return name == "TimeoutError" and attempt < self.max_retries
        return False

    def remaining(self, attempt: int) -> int:
        return max(0, self.max_retries - max(0, attempt))
