"""Knowledge Runtime adapter — wraps OKF; never vector RAG."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.acr.ir.bundles import KnowledgeBundle, KnowledgeItem
from neuroswarm_arm.runtime.acr.ir.plan import RetrievalExecutionPlan, RetrievalSource


def _estimate_tokens(text: str) -> int:
    return max(1, len((text or "").split()))


class KnowledgeRuntimeAdapter:
    """Thin adapter over OKFNexusRuntime / nexus_okf. Knowledge OS, not RAG."""

    def __init__(self, okf: Any | None = None) -> None:
        self._okf = okf

    def retrieve(
        self,
        plan: RetrievalExecutionPlan,
        *,
        agent_profile: str = "architect",
        tool_names: list[str] | None = None,
    ) -> KnowledgeBundle:
        bundle = KnowledgeBundle(request_id=plan.request_id)
        if self._okf is None:
            return bundle

        for step in plan.ordered_steps():
            if step.source == RetrievalSource.OKF:
                self._query_okf(bundle, step, agent_profile)
            elif step.source == RetrievalSource.POLICY:
                self._query_okf(bundle, step, agent_profile, kind="policy")
            elif step.source == RetrievalSource.TOOL_DOCS:
                names = list(tool_names or step.metadata.get("tools") or [])
                if not names and step.query:
                    names = step.query.split()
                self._tool_docs(bundle, names, step)
            bundle.source_step_ids.append(step.id)
        return bundle

    def _query_okf(
        self,
        bundle: KnowledgeBundle,
        step: Any,
        agent_profile: str,
        kind: str = "knowledge",
    ) -> None:
        try:
            budget = step.token_budget
            result = self._okf.query(
                step.query or "nexus overview",
                agent_profile=agent_profile,
            )
            # Some OKF wrappers accept token_budget on query via config only
            text = getattr(result, "text", "") or ""
            if not text:
                return
            # Progressive: prefer sections if present
            sections = getattr(result, "sections", None) or []
            if sections:
                used = 0
                for sec in sections:
                    st = getattr(sec, "text", "") or str(sec)
                    tok = int(getattr(sec, "tokens", 0) or _estimate_tokens(st))
                    if used + tok > budget:
                        break
                    bundle.items.append(
                        KnowledgeItem(
                            content=st,
                            path=str(getattr(sec, "path", "") or ""),
                            section_id=str(getattr(sec, "section_id", "") or getattr(sec, "id", "")),
                            score=float(getattr(sec, "score", step.priority) or step.priority),
                            kind=kind,
                            tokens=tok,
                            metadata={"step_id": step.id},
                        )
                    )
                    used += tok
            else:
                # Truncate to budget
                words = text.split()[:budget]
                clipped = " ".join(words)
                bundle.items.append(
                    KnowledgeItem(
                        content=clipped,
                        score=step.priority,
                        kind=kind,
                        tokens=_estimate_tokens(clipped),
                        metadata={"step_id": step.id, "tokens_used": getattr(result, "tokens_used", 0)},
                    )
                )
        except Exception:
            return

    def _tool_docs(self, bundle: KnowledgeBundle, names: list[str], step: Any) -> None:
        if not names or not hasattr(self._okf, "load_tool_docs"):
            return
        try:
            docs = self._okf.load_tool_docs(names, budget=step.token_budget)
            text = getattr(docs, "text", "") or ""
            if not text:
                return
            bundle.items.append(
                KnowledgeItem(
                    content=text,
                    kind="tool_docs",
                    score=step.priority,
                    tokens=_estimate_tokens(text),
                    metadata={"tools": names, "step_id": step.id},
                )
            )
        except Exception:
            return
