"""Append-only recovery history."""

from __future__ import annotations

from typing import Any

from .models import RecoveryRecord


class RecoveryHistory:
    """In-memory append-only store for RecoveryRecord."""

    def __init__(self) -> None:
        self._records: list[RecoveryRecord] = []

    def append(self, record: RecoveryRecord) -> None:
        self._records.append(record)

    def list(
        self,
        *,
        execution_id: str | None = None,
        limit: int | None = None,
    ) -> list[RecoveryRecord]:
        items = self._records
        if execution_id is not None:
            items = [r for r in items if r.execution_id == execution_id]
        if limit is not None:
            items = items[-limit:]
        return list(items)

    def latest(self, execution_id: str | None = None) -> RecoveryRecord | None:
        items = self.list(execution_id=execution_id)
        return items[-1] if items else None

    def success_rate(self, execution_id: str | None = None) -> float:
        items = self.list(execution_id=execution_id)
        if not items:
            return 0.0
        ok = sum(1 for r in items if r.recovery_success)
        return ok / len(items)

    def average_degradation(self, execution_id: str | None = None) -> float:
        items = self.list(execution_id=execution_id)
        if not items:
            return 0.0
        return sum(r.quality_delta for r in items) / len(items)

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [r.model_dump(mode="json") for r in self._records]
