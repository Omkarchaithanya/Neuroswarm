"""Observability helpers for RTG."""

from __future__ import annotations

import logging
from typing import Any

LOG = logging.getLogger("neuroswarm_arm.runtime.rtg")


def get_logger(name: str = "rtg") -> logging.Logger:
    return logging.getLogger(f"neuroswarm_arm.runtime.rtg.{name}")


def trace_decision(decision: Any) -> None:
    LOG.debug("rtg.decision action=%s reason=%s", getattr(decision, "action", None), getattr(decision, "reason", ""))
