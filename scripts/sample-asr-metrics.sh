#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/neuroswarm-arm"
export PYTHONPATH="${HOME}/neuroswarm-arm"
export NSA_TIER_SPEC_URL=http://127.0.0.1:8084
export NSA_LLAMA_N_PROBS_DEFAULT=5
export NSA_LLAMA_N_PROBS=0
export NSA_LLAMA_SLOT_KV_REUSE=0

python3 - <<'PY'
import asyncio
import os
from neuroswarm_arm.runtime.armcascade.interfaces.types import Proposal
from neuroswarm_arm.runtime.dipa.backends.llama_cpp.backend import (
    ASR_METRICS,
    LlamaCppBackend,
)
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest

ASR_METRICS.reset()
backend = LlamaCppBackend(name="tier2", base_url="http://127.0.0.1:8085", tier=2)
assert backend._spec_url

draft = Proposal.from_text(
    "Paris is the capital of France and a major European city",
    strategy="draft_model",
)

async def main() -> None:
    ctx = ExecutionContext(request=InferenceRequest(messages=[{"role": "user", "content": "hi"}]))
    chunks = []
    async for ch in backend.generate_with_logits_stream(
        [{"role": "user", "content": "What is the capital of France?"}],
        max_tokens=16,
        temperature=0.0,
        draft=draft,
        tau_floor=0.3,
        ctx=ctx,
    ):
        chunks.append(ch)
    print("chunks", len(chunks))
    print("ASR_METRICS", ASR_METRICS.snapshot())

asyncio.run(main())
PY

# Also copy latest run json name
ls -1t docs/evidence/spec_decode/run_*.json | head -1
