"""Reflection engine — lessons after workflow execution."""

from __future__ import annotations

from neuroswarm_arm.runtime.memory.schemas import MemoryRecord, MemoryType, ReflectionResult


class ReflectionEngine:
    def reflect(
        self,
        *,
        workflow_id: str = "",
        success: bool = True,
        failures: list[str] | None = None,
        tools_used: list[str] | None = None,
        notes: str = "",
        latency_ms: float = 0.0,
        cost: float = 0.0,
    ) -> ReflectionResult:
        failures = failures or []
        tools_used = tools_used or []
        lessons: list[str] = []
        improvements: list[str] = []
        strategies: list[str] = []
        if success:
            strategies.append("workflow completed successfully")
            if tools_used:
                strategies.append(f"effective tools: {', '.join(tools_used)}")
            if latency_ms > 0:
                lessons.append(f"completed in {latency_ms:.0f}ms")
        else:
            lessons.append("workflow failed — review recovery path")
            improvements.append("increase verification before cascade escalate")
        for f in failures:
            improvements.append(f"avoid failure: {f}")
        if notes:
            lessons.append(notes)
        if cost > 0.05:
            improvements.append("reduce cost via cheaper tier when confidence high")
        return ReflectionResult(
            lessons=lessons,
            failures=list(failures),
            improvements=improvements,
            successful_strategies=strategies,
        )

    def to_records(
        self,
        result: ReflectionResult,
        *,
        owner: str,
        workflow_id: str = "",
        origin_agent: str = "",
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        blobs = [
            ("lessons", result.lessons),
            ("failures", result.failures),
            ("improvements", result.improvements),
            ("strategies", result.successful_strategies),
        ]
        for kind, items in blobs:
            for item in items:
                records.append(
                    MemoryRecord(
                        content=f"[{kind}] {item}",
                        type=MemoryType.REFLECTION,
                        namespace="reflection/",
                        owner=owner,
                        workflow_id=workflow_id,
                        origin_agent=origin_agent,
                        tags=["reflection", kind],
                        importance=0.7,
                        metadata={"reflection_kind": kind, "reflection_score": 0.7},
                    )
                )
        return records
