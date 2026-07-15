"""BudgetContext — multi-dimension budget envelope snapshot + usage."""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from .exceptions import BudgetError
from .models import _Base


class BudgetUsage(_Base):
    """Consumed amounts across budget dimensions."""

    cost_usd: float = 0.0
    tokens: float = 0.0
    latency_ms: float = 0.0
    energy_j: float = 0.0
    memory_bytes: int = 0
    cpu_cores_s: float = 0.0
    reasoning_tokens: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "cost_usd",
        "tokens",
        "latency_ms",
        "energy_j",
        "cpu_cores_s",
        "reasoning_tokens",
    )
    @classmethod
    def _non_neg_f(cls, v: float) -> float:
        if v < 0:
            raise ValueError("usage must be >= 0")
        return v

    @field_validator("memory_bytes")
    @classmethod
    def _non_neg_i(cls, v: int) -> int:
        if v < 0:
            raise ValueError("memory_bytes must be >= 0")
        return v


class BudgetContext(_Base):
    """Limits + used counters visible to every agent / condition.

    Reflects a frozen ARMORA envelope when ``envelope_id`` + ``frozen`` set.
    Mid-flight mutations update ``used`` only — limits stay stable after freeze.
    """

    cost_usd_limit: float | None = None
    tokens_limit: float | None = None
    latency_ms_limit: float | None = None
    energy_j_limit: float | None = None
    memory_bytes_limit: int | None = None
    cpu_cores_s_limit: float | None = None
    reasoning_tokens_limit: float | None = None

    used: BudgetUsage = Field(default_factory=BudgetUsage)

    # Convenience aliases matching legacy task_graph BudgetContext field names
    cost_usd_used: float = 0.0
    tokens_used: float = 0.0
    latency_ms_used: float = 0.0
    energy_j_used: float = 0.0
    memory_bytes_used: int = 0
    reasoning_tokens_used: float = 0.0

    envelope_id: str | None = None
    frozen: bool = False
    energy_estimate_j: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sync_used_aliases(self) -> Self:
        # Keep flat aliases and nested used in sync when constructed with either form
        u = self.used
        if self.cost_usd_used and not u.cost_usd:
            u.cost_usd = self.cost_usd_used
        if self.tokens_used and not u.tokens:
            u.tokens = self.tokens_used
        if self.latency_ms_used and not u.latency_ms:
            u.latency_ms = self.latency_ms_used
        if self.energy_j_used and not u.energy_j:
            u.energy_j = self.energy_j_used
        if self.memory_bytes_used and not u.memory_bytes:
            u.memory_bytes = self.memory_bytes_used
        if self.reasoning_tokens_used and not u.reasoning_tokens:
            u.reasoning_tokens = self.reasoning_tokens_used
        # Push nested → flat
        object.__setattr__(self, "cost_usd_used", u.cost_usd)
        object.__setattr__(self, "tokens_used", u.tokens)
        object.__setattr__(self, "latency_ms_used", u.latency_ms)
        object.__setattr__(self, "energy_j_used", u.energy_j)
        object.__setattr__(self, "memory_bytes_used", u.memory_bytes)
        object.__setattr__(self, "reasoning_tokens_used", u.reasoning_tokens)
        return self

    @field_validator(
        "cost_usd_limit",
        "tokens_limit",
        "latency_ms_limit",
        "energy_j_limit",
        "cpu_cores_s_limit",
        "reasoning_tokens_limit",
        "energy_estimate_j",
    )
    @classmethod
    def _limit_non_neg(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("budget limit must be >= 0")
        return v

    @field_validator("memory_bytes_limit")
    @classmethod
    def _mem_limit(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("memory_bytes_limit must be >= 0")
        return v

    # ------------------------------------------------------------------ remaining
    def remaining_cost(self) -> float | None:
        if self.cost_usd_limit is None:
            return None
        return max(0.0, self.cost_usd_limit - self.cost_usd_used)

    def remaining_tokens(self) -> float | None:
        if self.tokens_limit is None:
            return None
        return max(0.0, self.tokens_limit - self.tokens_used)

    def remaining_latency_ms(self) -> float | None:
        if self.latency_ms_limit is None:
            return None
        return max(0.0, self.latency_ms_limit - self.latency_ms_used)

    def remaining_reasoning(self) -> float | None:
        if self.reasoning_tokens_limit is None:
            return None
        return max(0.0, self.reasoning_tokens_limit - self.reasoning_tokens_used)

    def remaining_memory(self) -> int | None:
        if self.memory_bytes_limit is None:
            return None
        return max(0, self.memory_bytes_limit - self.memory_bytes_used)

    def remaining_map(self) -> dict[str, float | int | None]:
        return {
            "cost_usd": self.remaining_cost(),
            "tokens": self.remaining_tokens(),
            "latency_ms": self.remaining_latency_ms(),
            "reasoning_tokens": self.remaining_reasoning(),
            "memory_bytes": self.remaining_memory(),
            "energy_j": (
                None
                if self.energy_j_limit is None
                else max(0.0, self.energy_j_limit - self.energy_j_used)
            ),
        }

    def is_exhausted(self) -> bool:
        for v in self.remaining_map().values():
            if v is not None and v <= 0:
                return True
        return False

    def apply_usage(
        self,
        *,
        cost_usd: float = 0.0,
        tokens: float = 0.0,
        latency_ms: float = 0.0,
        energy_j: float = 0.0,
        memory_bytes: int = 0,
        cpu_cores_s: float = 0.0,
        reasoning_tokens: float = 0.0,
    ) -> BudgetContext:
        """Return updated budget with usage applied (immutable-style copy)."""
        if any(
            x < 0
            for x in (
                cost_usd,
                tokens,
                latency_ms,
                energy_j,
                memory_bytes,
                cpu_cores_s,
                reasoning_tokens,
            )
        ):
            raise BudgetError("usage deltas must be >= 0", field="used")
        new_used = self.used.model_copy(
            update={
                "cost_usd": self.used.cost_usd + cost_usd,
                "tokens": self.used.tokens + tokens,
                "latency_ms": self.used.latency_ms + latency_ms,
                "energy_j": self.used.energy_j + energy_j,
                "memory_bytes": self.used.memory_bytes + memory_bytes,
                "cpu_cores_s": self.used.cpu_cores_s + cpu_cores_s,
                "reasoning_tokens": self.used.reasoning_tokens + reasoning_tokens,
            }
        )
        return self.model_copy(
            update={
                "used": new_used,
                "cost_usd_used": new_used.cost_usd,
                "tokens_used": new_used.tokens,
                "latency_ms_used": new_used.latency_ms,
                "energy_j_used": new_used.energy_j,
                "memory_bytes_used": new_used.memory_bytes,
                "reasoning_tokens_used": new_used.reasoning_tokens,
            }
        )

    def propagate(self) -> BudgetContext:
        """Child inherits limits + current used counters (shared remaining)."""
        return self.model_copy(deep=True)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
