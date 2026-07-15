"""Warm manager — asks AWPP connector, tracks pools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..interfaces.types import ExecutionPlan, InferenceRequest
from ..interfaces.warm import IWarmConnector
from .model_pool import ModelPool
from .session_pool import SessionPool

if TYPE_CHECKING:
    from ..kernel import DIPARuntime


class WarmManager:
    def __init__(
        self,
        connector: IWarmConnector,
        *,
        model_pool: ModelPool | None = None,
        session_pool: SessionPool | None = None,
        runner: DIPARuntime | None = None,
    ) -> None:
        self.connector = connector
        self.models = model_pool or ModelPool()
        self.sessions = session_pool or SessionPool()
        self._runner = runner

    def ensure(self, req: InferenceRequest, plan: ExecutionPlan) -> bool:
        model = plan.model
        if self.models.is_warm(model) or self.connector.is_warm(model):
            self.models.touch(model)
            if req.session_id:
                self.sessions.bind(req.session_id, model)
            return True
        warm = False
        if self._runner is not None:
            warm = bool(
                self._runner._run_async(self.connector.ensure_warm(req, plan))
            )
        else:
            import asyncio

            warm = bool(asyncio.run(self.connector.ensure_warm(req, plan)))
        if warm:
            self.models.mark_warm(model)
            if req.session_id:
                self.sessions.bind(req.session_id, model)
        return warm
