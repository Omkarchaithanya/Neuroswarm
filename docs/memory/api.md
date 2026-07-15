# NeuroMemory API

```python
from neuroswarm_arm.runtime.memory import build_memory_runtime, SearchQuery

mem = build_memory_runtime("work/memory")  # provider from NSA_MEM_PROVIDER

# Ingest
mem.remember_fact("User prefers Arm CPUs", owner="alice")
mem.remember_tool("success tool=web.search", owner="alice", metadata={"tool_id": "web.search"})
mem.remember_reasoning("used chain-of-thought", owner="alice")
mem.remember_workflow("dag=chat ok=true", owner="alice", workflow_id="chat")
mem.remember_execution("...", owner="alice")
mem.remember_cost("cost_usd=0.01", owner="alice", cost=0.01)
mem.remember_latency("latency_ms=120", owner="alice", latency=120)
mem.remember_performance("ttft_ms=40", owner="alice")
mem.remember_failure("tool timeout", owner="alice", failure_reason="timeout")
mem.remember_success("ok", owner="alice", success_score=1.0)
mem.remember_reflection("lesson: verify schemas", owner="alice")
mem.remember_experience("...", owner="alice")
mem.remember_prompt("system: ...", owner="alice")
mem.remember_benchmark("router@0.92", owner="alice")

# Retrieve
texts = mem.recall("alice", "Arm", limit=5)
hits = mem.search(SearchQuery(text="Arm", owner="alice", namespace="agents/", limit=5))
records = mem.retrieve(SearchQuery(text="Arm", owner="alice"))

# Lifecycle / cognition
mem.archive(id)
mem.forget(id)
mem.compress("alice", keep=100)
mem.summarize(id)
mem.predict_next("alice", context="next tool")
mem.reflect(owner="alice", workflow_id="chat", success=True, tools_used=["web.search"])
mem.rank(hits)
mem.promote(id)
mem.demote(id)
mem.link(a, b, rel="related")
mem.merge(a, b)
mem.health()
```

**Rule:** never `import mem0` outside `neuroswarm_arm.runtime.memory.mem0`.
