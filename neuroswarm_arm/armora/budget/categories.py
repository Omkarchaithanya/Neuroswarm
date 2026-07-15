"""Budget category dimensions — limit / consumed / remaining / estimated / projected."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .schemas import Hardness, ViolationState


class BudgetCategory(BaseModel):
    """Base runtime category with shared accounting fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str
    unit: str
    limit: float = 0.0
    consumed: float = 0.0
    reserved: float = 0.0
    estimated: float = 0.0
    projected: float = 0.0
    confidence: float = 1.0
    hardness: Hardness = Hardness.HARD
    violation: ViolationState = ViolationState.NONE
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def remaining(self) -> float:
        return max(0.0, float(self.limit) - float(self.consumed) - float(self.reserved))

    def refresh_violation(self) -> ViolationState:
        used = float(self.consumed) + float(self.reserved)
        if used > float(self.limit) + 1e-12:
            self.violation = (
                ViolationState.BREACHED
                if self.hardness is Hardness.HARD
                else ViolationState.WARNING
            )
        elif float(self.projected) > float(self.limit) + 1e-12:
            self.violation = ViolationState.WARNING
        else:
            self.violation = ViolationState.NONE
        return self.violation

    def apply_consume(self, amount: float) -> None:
        self.consumed = max(0.0, float(self.consumed) + float(amount))
        self.refresh_violation()

    def apply_reserve(self, amount: float) -> None:
        self.reserved = max(0.0, float(self.reserved) + float(amount))
        self.refresh_violation()

    def release_reserve(self, amount: float) -> None:
        self.reserved = max(0.0, float(self.reserved) - float(amount))
        self.refresh_violation()

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "limit": self.limit,
            "consumed": self.consumed,
            "reserved": self.reserved,
            "remaining": self.remaining,
            "estimated": self.estimated,
            "projected": self.projected,
            "confidence": self.confidence,
            "hardness": self.hardness.value,
            "violation": self.violation.value,
        }


class LatencyBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "latency_ms")
        data.setdefault("unit", "ms")
        super().__init__(**data)


class CostBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "cost_usd")
        data.setdefault("unit", "usd")
        super().__init__(**data)


class TokenBudget(BudgetCategory):
    """Parent token ceiling; sub-ledgers tracked as sibling categories."""

    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "tokens_total")
        data.setdefault("unit", "tokens")
        super().__init__(**data)


class PromptTokenBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "prompt_tokens")
        data.setdefault("unit", "tokens")
        super().__init__(**data)


class CompletionTokenBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "completion_tokens")
        data.setdefault("unit", "tokens")
        super().__init__(**data)


class ReasoningTokenBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "reasoning_tokens")
        data.setdefault("unit", "tokens")
        super().__init__(**data)


class MemoryBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "memory_bytes")
        data.setdefault("unit", "bytes")
        super().__init__(**data)


class EnergyBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "energy_joules")
        data.setdefault("unit", "joules")
        super().__init__(**data)


class KVBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "kv_bytes")
        data.setdefault("unit", "bytes")
        super().__init__(**data)


class ToolBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "tool_calls")
        data.setdefault("unit", "count")
        super().__init__(**data)


class ComputeBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "cpu_seconds")
        data.setdefault("unit", "seconds")
        super().__init__(**data)


class StreamingBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "streaming_ms")
        data.setdefault("unit", "ms")
        super().__init__(**data)


class RetryBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "retries")
        data.setdefault("unit", "count")
        super().__init__(**data)


class ConcurrencyBudget(BudgetCategory):
    def __init__(self, **data: Any) -> None:
        data.setdefault("name", "concurrency")
        data.setdefault("unit", "count")
        super().__init__(**data)


CATEGORY_FACTORIES: dict[str, type[BudgetCategory]] = {
    "latency_ms": LatencyBudget,
    "cost_usd": CostBudget,
    "tokens_total": TokenBudget,
    "prompt_tokens": PromptTokenBudget,
    "completion_tokens": CompletionTokenBudget,
    "reasoning_tokens": ReasoningTokenBudget,
    "memory_bytes": MemoryBudget,
    "energy_joules": EnergyBudget,
    "kv_bytes": KVBudget,
    "tool_calls": ToolBudget,
    "cpu_seconds": ComputeBudget,
    "streaming_ms": StreamingBudget,
    "retries": RetryBudget,
    "concurrency": ConcurrencyBudget,
}


def build_category(
    name: str,
    *,
    limit: float,
    hardness: Hardness = Hardness.HARD,
    unit: str | None = None,
    **kwargs: Any,
) -> BudgetCategory:
    cls = CATEGORY_FACTORIES.get(name, BudgetCategory)
    data: dict[str, Any] = {"name": name, "limit": float(limit), "hardness": hardness, **kwargs}
    if unit is not None:
        data["unit"] = unit
    elif cls is BudgetCategory:
        data.setdefault("unit", "unit")
    return cls(**data)
