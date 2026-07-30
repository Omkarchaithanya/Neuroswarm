"""End-to-end ASCR round-trip with synthetic logits mock backend."""

from __future__ import annotations

import asyncio
from typing import Any

from neuroswarm_arm.runtime.armcascade.config.loader import load_ascr_config, parse_escalation_graphs
from neuroswarm_arm.runtime.armcascade.engine import ASCREngine
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    Proposal,
    ProposalToken,
    VerifyMode,
    VerifyRequest,
)
from neuroswarm_arm.runtime.armcascade.proposal import draft_model as _draft  # noqa: F401
from neuroswarm_arm.runtime.armcascade.verification import logits_verifier as _logits  # noqa: F401
from neuroswarm_arm.runtime.armcascade.verification import strategies as _verify  # noqa: F401
from neuroswarm_arm.runtime.armcascade.verification.logits_verifier import LogitsAcceptanceVerifier
from neuroswarm_arm.runtime.dipa.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.dipa.interfaces.types import (
    ExecutionPlan,
    GenerateRequest,
    GenerateResult,
    InferenceRequest,
)
from tests.runtime.armcascade.test_logits_verifier import _raw_openai_logprobs


class _RoundTripBackend:
    def __init__(self, name: str, tier: int) -> None:
        self.name = name
        self.tier = tier

    async def generate(self, req: GenerateRequest, ctx: Any) -> GenerateResult:
        words = ["Paris", "is", "the", "capital"]
        text = " ".join(words)
        return GenerateResult(
            text=text,
            backend=self.name,
            tier_used=self.tier,
            raw={"choices": [{"message": {"content": text}}]},
            metrics={},
        )

    async def generate_with_logits(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        top_logprobs: int,
        session_id: str = "",
        quant: str = "",
        kv_handle: str | None = None,
        ctx: Any = None,
    ) -> GenerateResult:
        steps = [
            ("Paris", [("Paris", -0.1, 1), ("London", -1.0, 2)]),
            ("is", [("is", -0.1, 10), ("was", -1.0, 11)]),
            ("the", [("the", -0.1, 20), ("a", -1.0, 21)]),
            ("capital", [("capital", -0.1, 30), ("city", -1.0, 31)]),
        ]
        raw = _raw_openai_logprobs(steps[:max(max_tokens, 1)])
        text = " ".join(s[0] for s in steps[:max(max_tokens, 1)])
        return GenerateResult(
            text=text,
            backend=self.name,
            tier_used=self.tier,
            raw=raw,
            metrics={"logits_available": 1.0},
        )


class _Registry:
    def __init__(self, backends: dict[str, _RoundTripBackend]) -> None:
        self._backends = backends

    def require(self, name: str) -> _RoundTripBackend:
        return self._backends[name]


def test_build_ascr_logits_round_trip() -> None:
    backends = {
        "tier1": _RoundTripBackend("tier1", 1),
        "tier2": _RoundTripBackend("tier2", 2),
        "tier3": _RoundTripBackend("tier3", 3),
    }
    cfg = load_ascr_config()
    graphs = parse_escalation_graphs(cfg.get("escalation_graphs"))
    engine = ASCREngine(
        config=cfg,
        registry=_Registry(backends),
        graphs=graphs,
    )
    plan = ExecutionPlan(
        model="tier1",
        backend="tier1",
        use_cascade=True,
        speculation=True,
        self_speculation=True,
        cascade_start_tier=1,
        metadata={
            "speculation": {
                "strategy": "draft_model",
                "verify_strategy": "logits",
                "graph": "default_linear",
                "draft_len": 4,
            }
        },
    )
    req = InferenceRequest(
        messages=[{"role": "user", "content": "What is the capital?"}],
        max_tokens=32,
        session_id="logits-round-trip",
    )
    ctx = ExecutionContext(request=req)
    result = asyncio.run(engine.run(req, plan, ctx))
    assert bool(result.raw.get("logits_available"))

    verifier = LogitsAcceptanceVerifier()
    asyncio.run(
        verifier.initialize(ASCRInitContext(registry=_Registry(backends), config=cfg))
    )
    draft = Proposal(
        tokens=[
            ProposalToken(text="Paris", token_id=1, logprob=-0.1, rank=0),
            ProposalToken(text="is", token_id=10, logprob=-0.1, rank=0),
            ProposalToken(text="the", token_id=20, logprob=-0.1, rank=0),
            ProposalToken(text="capital", token_id=30, logprob=-0.1, rank=0),
        ],
        text="Paris is the capital",
        strategy="draft_model",
        draft_len=4,
        confidence=0.7,
        source_tier=1,
    )
    vreq = VerifyRequest(
        messages=[{"role": "user", "content": "What is the capital?"}],
        prompt_text="What is the capital?",
        temperature=0.0,
    )
    vres = asyncio.run(verifier.verify(draft, vreq))
    assert vres.logits_available
    assert vres.mode == VerifyMode.LOGITS
    assert vres.accepted_prefix_len == 4
