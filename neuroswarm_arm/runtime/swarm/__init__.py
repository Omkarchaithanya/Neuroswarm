"""Swarm runtime primitives for NEXUS-ARM.

Subsystems:

- ``neuroswarm_arm.runtime.swarm.task_graph`` — DAG plan + executor
- ``neuroswarm_arm.runtime.swarm.context`` — Context Operating System
- ``neuroswarm_arm.runtime.swarm.agent_registry`` — agent capability catalog
- ``neuroswarm_arm.runtime.swarm.meta_orchestrator`` — workflow coordinator
- ``neuroswarm_arm.runtime.swarm.sub_swarms`` — reusable workflow templates
"""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.context import (
    CONTEXT_SCHEMA_VERSION,
    SwarmContext,
    SwarmContextBuilder,
    SwarmContextSnapshot,
    child_context,
    create_snapshot,
    dumps,
    loads,
    merge_contexts,
    restore_snapshot,
)
from neuroswarm_arm.runtime.swarm.meta_orchestrator import (
    MetaOrchestrator,
    WorkflowBuilder,
    WorkflowExecution,
    WorkflowStatus,
    build_meta_orchestrator,
)

__all__ = [
    "SwarmContext",
    "SwarmContextBuilder",
    "SwarmContextSnapshot",
    "CONTEXT_SCHEMA_VERSION",
    "child_context",
    "create_snapshot",
    "restore_snapshot",
    "merge_contexts",
    "dumps",
    "loads",
    # Meta Orchestrator (additive)
    "MetaOrchestrator",
    "WorkflowBuilder",
    "WorkflowExecution",
    "WorkflowStatus",
    "build_meta_orchestrator",
]
