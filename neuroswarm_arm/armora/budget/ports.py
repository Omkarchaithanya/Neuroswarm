"""Ports / Protocols for hexagonal Budget Envelope architecture."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from .schemas import (
    AffordDecision,
    DimensionDelta,
    EnvelopeTemplate,
    PlanAction,
    ResourceProjection,
)


@runtime_checkable
class ICostModel(Protocol):
    def project(
        self,
        op: Mapping[str, Any],
        hardware: Mapping[str, Any] | None = None,
        cache_state: Mapping[str, Any] | None = None,
    ) -> ResourceProjection: ...


@runtime_checkable
class IEnergyModel(Protocol):
    def project(
        self,
        *,
        cpu_seconds: float,
        thread_count: int = 1,
        numa_node: int = 0,
        hardware: Mapping[str, Any] | None = None,
    ) -> ResourceProjection: ...


@runtime_checkable
class IEstimator(Protocol):
    def project_action(
        self,
        action: PlanAction,
        *,
        hardware: Mapping[str, Any] | None = None,
        cache_state: Mapping[str, Any] | None = None,
    ) -> ResourceProjection: ...

    def project_kv(
        self,
        *,
        layers: int,
        kv_heads: int,
        head_dim: int,
        seq_len: int,
        batch: int = 1,
        elem_size: int = 2,
    ) -> ResourceProjection: ...


@runtime_checkable
class IPersistence(Protocol):
    def write_envelope(self, envelope_id: str, payload: Mapping[str, Any]) -> None: ...

    def write_report(self, envelope_id: str, report_type: str, payload: Mapping[str, Any]) -> None: ...

    def query_history(self, *, tenant_id: str = "", limit: int = 100) -> list[Mapping[str, Any]]: ...


@runtime_checkable
class ITelemetryExporter(Protocol):
    def record_admit(self, *, accepted: bool, tenant: str = "", agent: str = "") -> None: ...

    def record_remaining(self, dim: str, value: float, *, scope: str = "request") -> None: ...

    def record_violation(self, dim: str, hardness: str) -> None: ...

    def record_estimate_error(self, dim: str, error: float) -> None: ...

    def record_degrade(self, action: str) -> None: ...

    def record_efficiency(self, *, tokens_per_usd: float, tokens_per_watt: float) -> None: ...

    def snapshot(self) -> Mapping[str, Any]: ...


@runtime_checkable
class IPolicyCompiler(Protocol):
    def compile(
        self,
        *,
        agent_role: str,
        tenant_id: str = "",
        overrides: Mapping[str, Any] | None = None,
    ) -> EnvelopeTemplate: ...


@runtime_checkable
class IAccountingProvider(Protocol):
    def record(self, envelope_id: str, delta: DimensionDelta) -> None: ...

    def tenant_snapshot(self, tenant_id: str) -> Mapping[str, float]: ...


@runtime_checkable
class IBudgetService(Protocol):
    async def create_and_freeze(
        self,
        *,
        request_id: str,
        tenant_id: str = "",
        agent_role: str = "default",
        agent_id: str = "",
        overrides: Mapping[str, Any] | None = None,
    ) -> Any: ...

    def can_afford(self, envelope_id: str, action: PlanAction) -> AffordDecision: ...

    async def finalize(self, envelope_id: str) -> Mapping[str, Any]: ...
