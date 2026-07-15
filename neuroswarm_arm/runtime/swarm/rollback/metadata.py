"""Execution metadata envelope for rollback operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._utils import utc_now
from .models import RollbackStatus, _Frozen


class RollbackExecutionMetadata(_Frozen):
    """Mutable-lifecycle-friendly metadata envelope around a rollback body."""

    rollback_id: str
    status: RollbackStatus = RollbackStatus.PENDING
    recorded_at: datetime = Field(default_factory=utc_now)
    validated_at: datetime | None = None
    prepared_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    cancelled_at: datetime | None = None
    duration_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
