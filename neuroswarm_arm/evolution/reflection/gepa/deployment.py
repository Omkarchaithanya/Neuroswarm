"""
Approval gate + text-only deployment for GEPA candidates.

Official GEPA stops at candidate acceptance into the pool/Pareto.
NEXUS adds Replay → … → Approval → Promotion → Deployment for production
safety (plan Step 11). Nothing auto-deploys without Approval.

ArmCascade/AROP: writes OKF/Mem0 text artifacts only — never RLAction knobs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from neuroswarm_arm.evolution.reflection.gepa.candidate.models import TextCandidate
from neuroswarm_arm.evolution.reflection.gepa.candidate.pool import CandidatePool


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approved: bool
    candidate_id: str
    reviewer: str
    reason: str
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalGate:
    """Explicit human/system approval required before GEPA text promotion."""

    def __init__(self) -> None:
        self._pending: dict[str, TextCandidate] = {}
        self._decisions: list[ApprovalDecision] = []

    def submit(self, candidate: TextCandidate) -> None:
        self._pending[candidate.id] = candidate

    def approve(self, candidate_id: str, *, reviewer: str = "operator", reason: str = "approved") -> ApprovalDecision:
        if candidate_id not in self._pending and candidate_id not in {c.id for c in []}:
            # allow approve of known id even if not pending
            pass
        decision = ApprovalDecision(
            approved=True,
            candidate_id=candidate_id,
            reviewer=reviewer,
            reason=reason,
        )
        self._decisions.append(decision)
        self._pending.pop(candidate_id, None)
        return decision

    def reject(self, candidate_id: str, *, reviewer: str = "operator", reason: str = "rejected") -> ApprovalDecision:
        decision = ApprovalDecision(
            approved=False,
            candidate_id=candidate_id,
            reviewer=reviewer,
            reason=reason,
        )
        self._decisions.append(decision)
        self._pending.pop(candidate_id, None)
        return decision

    def is_approved(self, candidate_id: str) -> bool:
        for d in reversed(self._decisions):
            if d.candidate_id == candidate_id:
                return d.approved
        return False

    def pending(self) -> list[TextCandidate]:
        return list(self._pending.values())


class TextArtifactDeployer:
    """
    Deploy approved TextCandidate components to OKF + Mem0.

    Maps to AROP deployment for *text* — not ASCR RLAction thresholds.
    """

    def __init__(
        self,
        *,
        okf_root: Path | None = None,
        memory: Any | None = None,
        pool: CandidatePool | None = None,
    ) -> None:
        self.okf_root = Path(okf_root or "okf")
        self.memory = memory
        self.pool = pool

    def deploy(self, candidate: TextCandidate, *, require_approval: bool = True, gate: ApprovalGate | None = None) -> dict[str, Any]:
        if require_approval:
            if gate is None or not gate.is_approved(candidate.id):
                return {
                    "success": False,
                    "message": "approval required before GEPA text deployment",
                    "candidate_id": candidate.id,
                }
        written: list[str] = []
        try:
            from neuroswarm_arm.runtime.okf.connectors.evolution_sink import write_evolved_prompt

            for name, body in candidate.components.items():
                rel = f"domains/architecture/gepa/{candidate.id}/{name}.md"
                path = write_evolved_prompt(
                    self.okf_root,
                    rel,
                    body,
                    frontmatter={
                        "type": "gepa_component",
                        "title": f"GEPA {name}",
                        "okf_version": "1.0",
                        "gepa_candidate_id": candidate.id,
                        "gepa_version": candidate.version,
                        "content_hash": candidate.content_hash,
                        "component": name,
                    },
                )
                written.append(str(path))
        except Exception as exc:
            return {"success": False, "message": str(exc), "candidate_id": candidate.id}

        neuro = getattr(self.memory, "neuro", self.memory) if self.memory is not None else None
        if neuro is not None and hasattr(neuro, "remember_evolution"):
            try:
                neuro.remember_evolution(
                    f"gepa_deploy:{candidate.id}:{candidate.content_hash}:{json.dumps(list(candidate.components.keys()))}",
                    owner="gepa",
                    tags=["gepa", "deploy", candidate.id],
                )
            except Exception:
                pass

        deployed = candidate.mark_deployed()
        if self.pool is not None:
            try:
                self.pool.replace_same_id(deployed)
            except Exception:
                self.pool.add(deployed)

        return {
            "success": True,
            "candidate_id": candidate.id,
            "paths": written,
            "message": "deployed text artifacts to OKF/Mem0",
        }

    def remember_reflection(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        neuro = getattr(self.memory, "neuro", self.memory) if self.memory is not None else None
        if neuro is None:
            return
        try:
            if hasattr(neuro, "remember_reflection"):
                neuro.remember_reflection(text, owner="gepa", **(metadata or {}))
            elif hasattr(neuro, "remember_evolution"):
                neuro.remember_evolution(text, owner="gepa", tags=["gepa", "reflection"])
        except Exception:
            return
