"""Runtime phase state machine for the HAOE kernel."""

from __future__ import annotations

from threading import RLock

from ..interfaces.types import RuntimePhase, TaskState, TASK_TRANSITIONS


RUNTIME_TRANSITIONS: dict[RuntimePhase, frozenset[RuntimePhase]] = {
    RuntimePhase.CREATED: frozenset({RuntimePhase.STARTING, RuntimePhase.FAILED}),
    RuntimePhase.STARTING: frozenset(
        {RuntimePhase.RUNNING, RuntimePhase.FAILED, RuntimePhase.STOPPED}
    ),
    RuntimePhase.RUNNING: frozenset(
        {RuntimePhase.DRAINING, RuntimePhase.STOPPED, RuntimePhase.FAILED}
    ),
    RuntimePhase.DRAINING: frozenset(
        {RuntimePhase.STOPPED, RuntimePhase.FAILED, RuntimePhase.RUNNING}
    ),
    RuntimePhase.STOPPED: frozenset({RuntimePhase.STARTING, RuntimePhase.CREATED}),
    RuntimePhase.FAILED: frozenset({RuntimePhase.STARTING, RuntimePhase.STOPPED}),
}


class InvalidTransition(ValueError):
    pass


class RuntimeStateMachine:
    """Thread-safe kernel lifecycle."""

    def __init__(self, initial: RuntimePhase = RuntimePhase.CREATED) -> None:
        self._phase = initial
        self._lock = RLock()

    @property
    def phase(self) -> RuntimePhase:
        with self._lock:
            return self._phase

    def transition(self, target: RuntimePhase) -> RuntimePhase:
        with self._lock:
            allowed = RUNTIME_TRANSITIONS.get(self._phase, frozenset())
            if target not in allowed:
                raise InvalidTransition(
                    f"illegal runtime transition {self._phase.value} -> {target.value}"
                )
            self._phase = target
            return self._phase

    def is_accepting_work(self) -> bool:
        return self.phase is RuntimePhase.RUNNING


class TaskStateMachine:
    """Per-task lifecycle with validated transitions."""

    def __init__(self, initial: TaskState = TaskState.QUEUED) -> None:
        self._state = initial
        self._lock = RLock()

    @property
    def state(self) -> TaskState:
        with self._lock:
            return self._state

    def transition(self, target: TaskState) -> TaskState:
        with self._lock:
            allowed = TASK_TRANSITIONS.get(self._state, frozenset())
            if target not in allowed:
                raise InvalidTransition(
                    f"illegal task transition {self._state.value} -> {target.value}"
                )
            self._state = target
            return self._state

    def force(self, target: TaskState) -> TaskState:
        """Admin/recovery path — bypasses transition table."""
        with self._lock:
            self._state = target
            return self._state
