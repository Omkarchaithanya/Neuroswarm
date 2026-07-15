"""Structured JSON logging bound to RuntimeTraceContext."""

from __future__ import annotations

import json
import sys
import threading
from typing import Any, Callable, Mapping

from .context import get_current_context
from .schemas import LogRecord


class StructuredLogger:
    """JSON-only logger; every record merges active RuntimeTraceContext."""

    def __init__(
        self,
        *,
        level: str = "INFO",
        on_log: Callable[[LogRecord], None] | None = None,
        stream: Any | None = None,
    ) -> None:
        self.level = level.upper()
        self.on_log = on_log
        self.stream = stream or sys.stderr
        self._lock = threading.Lock()
        self._levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    def _enabled(self, level: str) -> bool:
        return self._levels.get(level.upper(), 20) >= self._levels.get(self.level, 20)

    def log(
        self,
        level: str,
        message: str,
        *,
        extra: Mapping[str, Any] | None = None,
        logger: str = "nexus.rof",
    ) -> None:
        if not self._enabled(level):
            return
        ctx = get_current_context()
        context_fields = ctx.to_log_fields() if ctx is not None else {}
        record = LogRecord(
            level=level.upper(),
            message=message,
            logger=logger,
            context=context_fields,
            extra=dict(extra or {}),
        )
        line = json.dumps(record.model_dump(mode="json"), default=str, separators=(",", ":"))
        with self._lock:
            try:
                self.stream.write(line + "\n")
                self.stream.flush()
            except Exception:
                pass
        if self.on_log is not None:
            try:
                self.on_log(record)
            except Exception:
                pass

    def debug(self, message: str, **kwargs: Any) -> None:
        self.log("DEBUG", message, extra=kwargs or None)

    def info(self, message: str, **kwargs: Any) -> None:
        self.log("INFO", message, extra=kwargs or None)

    def warning(self, message: str, **kwargs: Any) -> None:
        self.log("WARNING", message, extra=kwargs or None)

    def error(self, message: str, **kwargs: Any) -> None:
        self.log("ERROR", message, extra=kwargs or None)

    def critical(self, message: str, **kwargs: Any) -> None:
        self.log("CRITICAL", message, extra=kwargs or None)
