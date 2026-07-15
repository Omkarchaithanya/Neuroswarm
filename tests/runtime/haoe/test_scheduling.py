"""Unit tests for HAOE priority aging, work stealing, and queues."""

from __future__ import annotations

from neuroswarm_arm.runtime.haoe.interfaces.types import PoolKind, PriorityClass
from neuroswarm_arm.runtime.haoe.scheduling.queue_manager import QueueManager, QueuedTask
from neuroswarm_arm.runtime.haoe.scheduling.priority_scheduler import PriorityScheduler
from neuroswarm_arm.runtime.haoe.scheduling.work_stealing import WorkStealingScheduler


def test_work_steal_oldest_from_victim() -> None:
    queues = QueueManager()
    w1 = queues.register_worker(PoolKind.BACKGROUND, "w1")
    w2 = queues.register_worker(PoolKind.BACKGROUND, "w2")
    older = QueuedTask(task_id="old", pool=PoolKind.BACKGROUND)
    newer = QueuedTask(task_id="new", pool=PoolKind.BACKGROUND)
    queues.push_private(PoolKind.BACKGROUND, w1, older)
    queues.push_private(PoolKind.BACKGROUND, w1, newer)
    stealer = WorkStealingScheduler(queues, attempts=3)
    # w2 has empty private+overflow → steals from w1 (oldest = right side)
    stolen = stealer.take(w2, PoolKind.BACKGROUND)
    assert stolen is not None
    assert stolen.task_id == "old"
    assert stealer.steal_count >= 1


def test_priority_submit_and_depth() -> None:
    queues = QueueManager()
    queues.register_worker(PoolKind.INFERENCE, "inf-0")
    stealer = WorkStealingScheduler(queues)
    sched = PriorityScheduler(queues, stealer)
    sched.submit("t1", priority=PriorityClass.CRITICAL, pool=PoolKind.INFERENCE, payload=1)
    sched.submit("t2", priority=PriorityClass.BACKGROUND, pool=PoolKind.INFERENCE, payload=2)
    assert sched.depth(PoolKind.INFERENCE) == 2
    task = sched.poll("inf-0", PoolKind.INFERENCE)
    assert task is not None
    assert sched.depth(PoolKind.INFERENCE) == 1


def test_priority_aging_elevates_overflow() -> None:
    queues = QueueManager()
    stealer = WorkStealingScheduler(queues)
    sched = PriorityScheduler(queues, stealer, aging_enabled=True, aging_step=10.0)
    # No workers → overflow
    sched.submit("aged", priority=PriorityClass.BACKGROUND, pool=PoolKind.TOOL)
    overflow = queues._overflow[PoolKind.TOOL]
    assert len(overflow) == 1
    with overflow._lock:
        overflow._items[0].enqueued_at -= 5.0  # pretend waited 5s
    sched.age_pool(PoolKind.TOOL)
    with overflow._lock:
        assert overflow._items[0].effective_priority < float(int(PriorityClass.BACKGROUND))
