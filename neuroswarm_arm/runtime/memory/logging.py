"""Structured logging helpers for Cognitive Memory Runtime."""

from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger("neuroswarm.memory")


def get_logger(name: str = "neuroswarm.memory") -> logging.Logger:
    return logging.getLogger(name)


def log_event(event: str, **fields: Any) -> None:
    payload = " ".join(f"{k}={v!r}" for k, v in fields.items())
    _LOG.info("memory_event=%s %s", event, payload)
