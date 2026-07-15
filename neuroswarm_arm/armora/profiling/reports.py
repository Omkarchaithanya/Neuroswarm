"""Immutable RuntimeProfile builder."""

from __future__ import annotations

from typing import Any

from .metrics import affinity_from_values, get_float, heuristic_recommendations, merge_batches
from .schemas import (
    BackendMetrics,
    CPUMetrics,
    ExecutionMetrics,
    HardwareMetrics,
    MemoryMetrics,
    MetricBatch,
    NUMAMetrics,
    PhaseTimings,
    PlannerMetrics,
    ProfileSessionContext,
    ProfilingMode,
    RuntimeProfile,
    TelemetryMetadata,
)


class ProfileReportBuilder:
    def build(
        self,
        session: ProfileSessionContext,
        *,
        batches: list[MetricBatch],
        phases: PhaseTimings,
        profiler_used: str,
        recommendations: list[str] | None = None,
        warnings: list[str] | None = None,
        telemetry: TelemetryMetadata | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> RuntimeProfile:
        values = merge_batches(*batches)
        warn = list(warnings or [])
        recs = list(recommendations or [])
        recs.extend(heuristic_recommendations(values))
        # de-dupe preserve order
        seen: set[str] = set()
        uniq_recs: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                uniq_recs.append(r)

        cycles = get_float(values, "hardware.cycles")
        instr = get_float(values, "hardware.instructions")
        ipc = get_float(values, "hardware.ipc")
        if ipc <= 0 and cycles > 0:
            ipc = instr / cycles

        accepted = int(phases.accepted_speculative_tokens)
        rejected = int(phases.rejected_speculative_tokens)
        total_spec = accepted + rejected
        spec_ratio = (accepted / total_spec) if total_spec else 0.0

        affinity = affinity_from_values(values)

        return RuntimeProfile(
            request_id=session.request_id,
            execution_id=session.execution_id,
            workflow_id=session.workflow_id,
            agent_id=session.agent_id,
            envelope_id=session.envelope_id,
            tenant_id=session.tenant_id,
            profiler_used=profiler_used,
            sampling_frequency_hz=session.sampling_hz,
            mode=session.mode if isinstance(session.mode, ProfilingMode) else ProfilingMode.PRODUCTION,
            cpu=CPUMetrics(
                usage_percent=get_float(values, "cpu.usage_percent"),
                cpu_time_seconds=get_float(values, "cpu.cpu_time_seconds"),
                user_time_seconds=get_float(values, "cpu.user_time_seconds"),
                system_time_seconds=get_float(values, "cpu.system_time_seconds"),
                wall_time_ms=get_float(values, "cpu.wall_time_ms"),
                core_utilization=get_float(values, "cpu.core_utilization", "cpu.usage_percent"),
                frequency_mhz=get_float(values, "cpu.frequency_mhz"),
                thread_count=int(get_float(values, "cpu.thread_count")),
                context_switches=int(get_float(values, "cpu.context_switches")),
                affinity=affinity,
            ),
            memory=MemoryMetrics(
                rss_bytes=get_float(values, "memory.rss_bytes"),
                vms_bytes=get_float(values, "memory.vms_bytes"),
                peak_rss_bytes=get_float(
                    values, "memory.peak_rss_bytes", "memory.rss_bytes"
                ),
                average_rss_bytes=get_float(
                    values, "memory.average_rss_bytes", "memory.rss_bytes"
                ),
                percent=get_float(values, "memory.percent"),
            ),
            numa=NUMAMetrics(
                node=int(get_float(values, "numa.node")),
                nodes_available=max(1, int(get_float(values, "numa.nodes_available", default=1.0))),
            ),
            hardware=HardwareMetrics(
                cycles=cycles,
                instructions=instr,
                ipc=ipc,
                cache_misses=get_float(values, "hardware.cache_misses"),
                cache_references=get_float(values, "hardware.cache_references"),
                branch_misses=get_float(values, "hardware.branch_misses"),
                branch_instructions=get_float(values, "hardware.branch_instructions"),
                llc_loads=get_float(values, "hardware.llc_loads"),
                llc_misses=get_float(values, "hardware.llc_misses"),
                sve2_available=bool(get_float(values, "hardware.sve2_available")),
                i8mm_available=bool(get_float(values, "hardware.i8mm_available")),
                pmu_available=bool(get_float(values, "hardware.pmu_available")),
            ),
            backend=BackendMetrics(
                backend=phases.backend,
                model=phases.model,
                model_tier=phases.model_tier,
                quantization=phases.quantization,
                backend_time_ms=phases.backend_ms,
                model_loading_time_ms=phases.model_load_ms,
            ),
            planner=PlannerMetrics(
                planner_time_ms=phases.planner_ms,
                routing_time_ms=phases.routing_ms,
                queue_time_ms=phases.queue_ms,
            ),
            execution=ExecutionMetrics(
                execution_time_ms=phases.execution_ms,
                streaming_time_ms=phases.streaming_ms,
                tool_execution_time_ms=phases.tool_ms,
                kv_memory_bytes=phases.kv_memory_bytes,
                accepted_speculative_tokens=accepted,
                rejected_speculative_tokens=rejected,
                speculative_acceptance_ratio=spec_ratio,
            ),
            telemetry=telemetry or TelemetryMetadata(),
            warnings=warn,
            recommendations=uniq_recs,
            extensions=dict(extensions or {}),
        )
