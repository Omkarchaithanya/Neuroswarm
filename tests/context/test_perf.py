"""Light performance smoke for hash / clone / snapshot."""

from __future__ import annotations

import time

from neuroswarm_arm.runtime.swarm.context import (
    SwarmContextBuilder,
    create_snapshot,
)


def test_hash_clone_snapshot_perf():
    builder = SwarmContextBuilder().request(prompt="perf " * 50)
    for i in range(50):
        builder = builder  # keep chain
    ctx = (
        SwarmContextBuilder()
        .request(prompt="perf " * 200)
        .budget(cost_usd_limit=10.0, tokens_limit=100_000)
        .memory(working_memory={f"k{i}": f"v{i}" * 20 for i in range(100)})
        .execution(run_id="perf", pending_nodes=[f"n{i}" for i in range(50)])
        .knowledge(namespaces=[f"ns{i}" for i in range(20)])
        .tools(available_tools=[f"tool{i}" for i in range(30)])
        .build()
    )
    t0 = time.perf_counter()
    for _ in range(50):
        _ = ctx.content_hash()
        _ = ctx.clone()
        _ = create_snapshot(ctx)
    elapsed = time.perf_counter() - t0
    # Generous CI threshold — smoke only
    assert elapsed < 5.0, f"perf too slow: {elapsed:.3f}s"
