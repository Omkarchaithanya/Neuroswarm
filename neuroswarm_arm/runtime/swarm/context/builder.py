"""Fluent SwarmContextBuilder."""

from __future__ import annotations

from typing import Any

from ._utils import new_id, utc_now
from .budget import BudgetContext
from .context import SwarmContext
from .events import ContextCreated, EventBus
from .execution import ExecutionContext
from .knowledge import KnowledgeContext
from .memory import MemoryContext
from .metrics import ContextMetrics
from .models import ExternalRef, RegistryHandle, TaskGraphRef, TelemetryContext
from .request import RequestContext
from .tools import ToolContext
from .tracing import TraceContext
from .validators import assert_valid


class SwarmContextBuilder:
    """Fluent builder for production SwarmContext instances."""

    def __init__(self, *, events: EventBus | None = None, validate: bool = True) -> None:
        self._events = events
        self._validate = validate
        self._data: dict[str, Any] = {}

    def ids(
        self,
        *,
        swarm_id: str | None = None,
        request_id: str | None = None,
        workflow_id: str | None = None,
        execution_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> SwarmContextBuilder:
        for k, v in {
            "swarm_id": swarm_id,
            "request_id": request_id,
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "session_id": session_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
        }.items():
            if v is not None:
                self._data[k] = v
        return self

    def request(self, request: RequestContext | dict[str, Any] | None = None, **kwargs: Any) -> SwarmContextBuilder:
        if request is None:
            self._data["request"] = RequestContext(**kwargs)
        elif isinstance(request, dict):
            self._data["request"] = RequestContext(**{**request, **kwargs})
        else:
            self._data["request"] = request.model_copy(update=kwargs) if kwargs else request
        return self

    def budget(self, budget: BudgetContext | dict[str, Any] | None = None, **kwargs: Any) -> SwarmContextBuilder:
        if budget is None:
            self._data["budget"] = BudgetContext(**kwargs)
        elif isinstance(budget, dict):
            self._data["budget"] = BudgetContext(**{**budget, **kwargs})
        else:
            self._data["budget"] = budget.model_copy(update=kwargs) if kwargs else budget
        return self

    def memory(self, memory: MemoryContext | dict[str, Any] | None = None, **kwargs: Any) -> SwarmContextBuilder:
        if memory is None:
            self._data["memory"] = MemoryContext(**kwargs)
        elif isinstance(memory, dict):
            self._data["memory"] = MemoryContext(**{**memory, **kwargs})
        else:
            self._data["memory"] = memory.model_copy(update=kwargs) if kwargs else memory
        return self

    def execution(
        self, execution: ExecutionContext | dict[str, Any] | None = None, **kwargs: Any
    ) -> SwarmContextBuilder:
        if execution is None:
            self._data["execution"] = ExecutionContext(**kwargs)
        elif isinstance(execution, dict):
            self._data["execution"] = ExecutionContext(**{**execution, **kwargs})
        else:
            self._data["execution"] = execution.model_copy(update=kwargs) if kwargs else execution
        return self

    def knowledge(
        self, knowledge: KnowledgeContext | dict[str, Any] | None = None, **kwargs: Any
    ) -> SwarmContextBuilder:
        if knowledge is None:
            self._data["knowledge"] = KnowledgeContext(**kwargs)
        elif isinstance(knowledge, dict):
            self._data["knowledge"] = KnowledgeContext(**{**knowledge, **kwargs})
        else:
            self._data["knowledge"] = knowledge.model_copy(update=kwargs) if kwargs else knowledge
        return self

    def tools(self, tools: ToolContext | dict[str, Any] | None = None, **kwargs: Any) -> SwarmContextBuilder:
        if tools is None:
            self._data["tools"] = ToolContext(**kwargs)
        elif isinstance(tools, dict):
            self._data["tools"] = ToolContext(**{**tools, **kwargs})
        else:
            self._data["tools"] = tools.model_copy(update=kwargs) if kwargs else tools
        return self

    def metrics(
        self, metrics: ContextMetrics | dict[str, Any] | None = None, **kwargs: Any
    ) -> SwarmContextBuilder:
        if metrics is None:
            self._data["metrics"] = ContextMetrics(**kwargs)
        elif isinstance(metrics, dict):
            self._data["metrics"] = ContextMetrics(**{**metrics, **kwargs})
        else:
            self._data["metrics"] = metrics.model_copy(update=kwargs) if kwargs else metrics
        return self

    def tracing(
        self, tracing: TraceContext | dict[str, Any] | None = None, **kwargs: Any
    ) -> SwarmContextBuilder:
        if tracing is None:
            self._data["trace_context"] = TraceContext(**kwargs)
        elif isinstance(tracing, dict):
            self._data["trace_context"] = TraceContext(**{**tracing, **kwargs})
        else:
            self._data["trace_context"] = tracing.model_copy(update=kwargs) if kwargs else tracing
        return self

    def telemetry(
        self, telemetry: TelemetryContext | dict[str, Any] | None = None, **kwargs: Any
    ) -> SwarmContextBuilder:
        if telemetry is None:
            self._data["telemetry_context"] = TelemetryContext(**kwargs)
        elif isinstance(telemetry, dict):
            self._data["telemetry_context"] = TelemetryContext(**{**telemetry, **kwargs})
        else:
            self._data["telemetry_context"] = (
                telemetry.model_copy(update=kwargs) if kwargs else telemetry
            )
        return self

    def task_graph(self, ref: TaskGraphRef | dict[str, Any] | None = None, **kwargs: Any) -> SwarmContextBuilder:
        if ref is None:
            self._data["task_graph"] = TaskGraphRef(**kwargs)
        elif isinstance(ref, dict):
            self._data["task_graph"] = TaskGraphRef(**{**ref, **kwargs})
        else:
            self._data["task_graph"] = ref.model_copy(update=kwargs) if kwargs else ref
        return self

    def refs(
        self,
        *,
        mem0: ExternalRef | None = None,
        okf: ExternalRef | None = None,
        knowledge: ExternalRef | None = None,
        tool_registry: RegistryHandle | None = None,
        agent_registry: RegistryHandle | None = None,
    ) -> SwarmContextBuilder:
        if mem0 is not None:
            self._data["mem0_reference"] = mem0
        if okf is not None:
            self._data["okf_reference"] = okf
        if knowledge is not None:
            self._data["knowledge_reference"] = knowledge
        if tool_registry is not None:
            self._data["tool_registry"] = tool_registry
        if agent_registry is not None:
            self._data["agent_registry"] = agent_registry
        return self

    def tags(self, *tags: str) -> SwarmContextBuilder:
        existing = list(self._data.get("tags", []))
        existing.extend(tags)
        self._data["tags"] = existing
        return self

    def labels(self, **labels: str) -> SwarmContextBuilder:
        existing = dict(self._data.get("labels", {}))
        existing.update(labels)
        self._data["labels"] = existing
        return self

    def metadata(self, **meta: Any) -> SwarmContextBuilder:
        existing = dict(self._data.get("metadata", {}))
        existing.update(meta)
        self._data["metadata"] = existing
        return self

    def execution_plan(self, plan: dict[str, Any]) -> SwarmContextBuilder:
        self._data["execution_plan"] = dict(plan)
        return self

    def build(self, *, require_request: bool = False, require_execution: bool = False) -> SwarmContext:
        data = dict(self._data)
        if "swarm_id" not in data:
            data["swarm_id"] = new_id("sw_")
        if "execution" not in data:
            data["execution"] = ExecutionContext(run_id=new_id("run_"))
        elif not data["execution"].run_id:
            data["execution"] = data["execution"].model_copy(update={"run_id": new_id("run_")})
        now = utc_now()
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        ctx = SwarmContext.model_validate(data)
        ctx = ctx.sync_ids_from_trace().refresh_metrics()
        if self._validate:
            assert_valid(ctx, require_request=require_request, require_execution=require_execution)
        if self._events is not None:
            self._events.emit(ContextCreated(ctx.swarm_id, content_hash=ctx.content_hash()))
        return ctx
