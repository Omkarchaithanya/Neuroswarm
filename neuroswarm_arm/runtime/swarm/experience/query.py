"""Query engine over indexed Experience Store records."""

from __future__ import annotations

from typing import Callable

from .execution_record import ExecutionRecord
from .exceptions import NotFoundError
from .filters import ExperienceFilter, Predicate
from .indexing import ExperienceIndex
from .metrics import ExperienceMetrics
from .repository import IExperienceRepository


class QueryEngine:
    """Lookup and filter executions using secondary indexes when possible."""

    def __init__(
        self,
        repository: IExperienceRepository,
        *,
        metrics: ExperienceMetrics | None = None,
    ) -> None:
        self.repository = repository
        self.metrics = metrics or ExperienceMetrics()

    @property
    def index(self) -> ExperienceIndex:
        return self.repository.index()

    def get(self, execution_id: str) -> ExecutionRecord:
        self.metrics.incr("queries")
        return self.repository.get_execution(execution_id)

    def get_optional(self, execution_id: str) -> ExecutionRecord | None:
        self.metrics.incr("queries")
        try:
            return self.repository.get_execution(execution_id)
        except NotFoundError:
            return None

    def by_workflow(self, workflow_id: str) -> list[ExecutionRecord]:
        self.metrics.incr("queries")
        ids = self.index.by_workflow.get(workflow_id, set())
        return [self.index.by_execution[i] for i in ids if i in self.index.by_execution]

    def by_request(self, request_id: str) -> list[ExecutionRecord]:
        self.metrics.incr("queries")
        ids = self.index.by_request.get(request_id, set())
        return [self.index.by_execution[i] for i in ids if i in self.index.by_execution]

    def by_agent(self, agent_id: str) -> list[ExecutionRecord]:
        self.metrics.incr("queries")
        ids = self.index.by_agent.get(agent_id, set())
        return [self.index.by_execution[i] for i in ids if i in self.index.by_execution]

    def by_model(self, model: str) -> list[ExecutionRecord]:
        self.metrics.incr("queries")
        ids = self.index.by_model.get(model, set())
        return [self.index.by_execution[i] for i in ids if i in self.index.by_execution]

    def by_backend(self, backend: str) -> list[ExecutionRecord]:
        self.metrics.incr("queries")
        ids = self.index.by_backend.get(backend, set())
        return [self.index.by_execution[i] for i in ids if i in self.index.by_execution]

    def by_success(self, success: bool = True) -> list[ExecutionRecord]:
        self.metrics.incr("queries")
        ids = self.index.by_success.get(success, set())
        return [self.index.by_execution[i] for i in ids if i in self.index.by_execution]

    def filter(
        self,
        filt: ExperienceFilter | None = None,
        *,
        predicate: Predicate | None = None,
    ) -> list[ExecutionRecord]:
        self.metrics.incr("queries")
        candidates = self._candidate_ids(filt)
        if candidates is None:
            records = list(self.index.by_execution.values())
        else:
            records = [
                self.index.by_execution[i]
                for i in candidates
                if i in self.index.by_execution
            ]
        if filt is not None:
            records = filt.apply(records)
        if predicate is not None:
            records = [r for r in records if predicate(r)]
        return records

    def all(self) -> list[ExecutionRecord]:
        self.metrics.incr("queries")
        return list(self.index.by_execution.values())

    def count(self, filt: ExperienceFilter | None = None) -> int:
        return len(self.filter(filt))

    def _candidate_ids(self, filt: ExperienceFilter | None) -> set[str] | None:
        """Narrow via indexes; None means full scan."""
        if filt is None:
            return None
        idx = self.index
        sets: list[set[str]] = []
        if filt.workflow_id is not None:
            sets.append(set(idx.by_workflow.get(filt.workflow_id, set())))
        if filt.request_id is not None:
            sets.append(set(idx.by_request.get(filt.request_id, set())))
        if filt.agent_id is not None:
            sets.append(set(idx.by_agent.get(filt.agent_id, set())))
        if filt.model is not None:
            sets.append(set(idx.by_model.get(filt.model, set())))
        if filt.backend is not None:
            sets.append(set(idx.by_backend.get(filt.backend, set())))
        if filt.success is not None:
            sets.append(set(idx.by_success.get(filt.success, set())))
        if filt.tag is not None:
            sets.append(set(idx.by_tag.get(filt.tag, set())))
        if not sets:
            return None
        result = sets[0]
        for s in sets[1:]:
            result &= s
        return result

    async def afilter(
        self,
        filt: ExperienceFilter | None = None,
        *,
        predicate: Predicate | None = None,
    ) -> list[ExecutionRecord]:
        import asyncio

        return await asyncio.to_thread(self.filter, filt, predicate=predicate)
