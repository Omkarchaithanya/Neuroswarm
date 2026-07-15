# ASCR Plugin Guide

## Add a proposal strategy

1. Create class implementing `ProposalStrategy`.
2. Decorate with `@register_proposer("my_algo")`.
3. Enable in `config/strategies.yaml`.
4. Select via YAML `defaults.proposal_strategy`, plan metadata, or `NSA_ASCR_DEFAULT_PROPOSER`.

```python
from neuroswarm_arm.runtime.armcascade.interfaces.proposal import ProposalStrategy
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext, Proposal, ProposalRequest,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_proposer

@register_proposer("my_algo")
class MyAlgoProposer(ProposalStrategy):
    name = "my_algo"

    async def initialize(self, ctx: ASCRInitContext) -> None:
        ...

    async def propose(self, req: ProposalRequest) -> Proposal:
        return Proposal.from_text("...", strategy=self.name, confidence=0.5)

    def estimate_confidence(self, proposal: Proposal) -> float:
        return proposal.confidence
```

Import the module from `plugins/__init__.py` so registration runs at bootstrap.

## Add a verifier

Same pattern with `@register_verifier("my_verify")` and `VerifierStrategy.verify()`.

## Stub rule

Future algorithms (EAGLE, Medusa, PARD, tree verify) ship as registered stubs that raise `NotImplementedError` with a clear reason until weights/config exist. ASCREngine catches stub errors and degrades to quality-cascade when configured.
