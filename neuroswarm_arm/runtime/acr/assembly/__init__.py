"""Context Assembly Engine — linker producing FinalStructuredPrompt / Snapshot."""

from __future__ import annotations

from neuroswarm_arm.runtime.acr.ir.bundles import KnowledgeBundle, MemoryBundle
from neuroswarm_arm.runtime.acr.ir.context import (
    AssembledSection,
    ContextSnapshot,
    FinalStructuredPrompt,
    ProvenanceRef,
)
from neuroswarm_arm.runtime.acr.ir.plan import AssemblyPlan
from neuroswarm_arm.runtime.acr.ir.requirement import ContextRequirementGraph
from neuroswarm_arm.runtime.acr.ir.stats import ContextStatistics


def _tokens(text: str) -> int:
    return max(1, len((text or "").split()))


class AssemblyEngine:
    """Linker: order, budget, citations, stable prefix for prompt caching."""

    def assemble(
        self,
        memory: MemoryBundle,
        knowledge: KnowledgeBundle,
        plan: AssemblyPlan,
        *,
        request_id: str,
        plan_id: str,
        graph: ContextRequirementGraph,
        tool_prompt_block: str = "",
        stats: ContextStatistics | None = None,
    ) -> ContextSnapshot:
        sections: list[AssembledSection] = []
        provenance: list[ProvenanceRef] = []
        used = 0
        budget = plan.token_budget

        builders = {
            "policies": lambda: self._from_know(knowledge, "policy", "Institutional Policies"),
            "knowledge": lambda: self._from_know(knowledge, "knowledge", "Institutional Knowledge (OKF)"),
            "memories": lambda: self._from_mem(memory, None, "Recent Facts (Mem0)"),
            "reflections": lambda: self._from_mem(memory, "reflection", "Reflections"),
            "reasoning": lambda: self._from_mem(memory, "reasoning", "Reasoning Traces"),
            "tools": lambda: self._tools(knowledge, tool_prompt_block),
            "examples": lambda: self._from_mem(memory, "examples", "Examples"),
            "workflows": lambda: self._from_mem(memory, "workflow", "Workflows"),
            "instructions": lambda: (
                AssembledSection(
                    name="instructions",
                    text=f"## Task Intent\nIntent: {graph.intent}\nRole: {graph.agent_role}",
                    priority=1.0,
                    tokens=0,
                ),
                [],
            ),
        }

        order = list(plan.section_order)
        if plan.stable_prefix:
            # Cache-friendly: instructions + policies + knowledge first (immutable-ish)
            preferred = ["instructions", "policies", "knowledge"]
            order = preferred + [s for s in order if s not in preferred]

        for name in order:
            fn = builders.get(name)
            if not fn:
                continue
            section, prov = fn()
            if section is None or not (section.text or "").strip():
                continue
            section.tokens = section.tokens or _tokens(section.text)
            if used + section.tokens > budget and sections:
                # Trim section to remaining budget
                remain = budget - used
                if remain < 20:
                    break
                words = section.text.split()[:remain]
                section.text = " ".join(words)
                section.tokens = _tokens(section.text)
            used += section.tokens
            if plan.include_citations and prov:
                section.citations = [p.ref_id for p in prov if p.ref_id]
            sections.append(section)
            provenance.extend(prov)

        text = "\n\n".join(s.text for s in sections if s.text)
        final = FinalStructuredPrompt(text=text, sections=sections, token_count=_tokens(text))
        st = stats or ContextStatistics()
        st.output_tokens = final.token_count
        st.memory_items = len(memory.items)
        st.knowledge_items = len(knowledge.items)
        return ContextSnapshot(
            request_id=request_id,
            plan_id=plan_id,
            prompt=final.text,
            sections=sections,
            provenance=provenance,
            stats=st,
            metadata={"agent_role": graph.agent_role, "intent": graph.intent},
        )

    def _from_mem(
        self, bundle: MemoryBundle, memory_type: str | None, title: str
    ) -> tuple[AssembledSection | None, list[ProvenanceRef]]:
        items = bundle.items
        if memory_type:
            items = [i for i in items if memory_type in (i.memory_type or "") or memory_type in (i.namespace or "")]
        if not items:
            return None, []
        lines = [f"- {i.content}" for i in items]
        text = f"## {title}\n" + "\n".join(lines)
        prov = [
            ProvenanceRef(kind="memory", ref_id=i.memory_id or f"mem-{idx}", score=i.score)
            for idx, i in enumerate(items)
        ]
        return AssembledSection(name=title.split()[0].lower(), text=text, priority=0.8, tokens=_tokens(text)), prov

    def _from_know(
        self, bundle: KnowledgeBundle, kind: str, title: str
    ) -> tuple[AssembledSection | None, list[ProvenanceRef]]:
        if kind == "policy":
            items = [i for i in bundle.items if i.kind == "policy"]
        else:
            items = [i for i in bundle.items if i.kind in ("knowledge", "policy")]
            # Prefer non-tool institutional body for knowledge section
            items = [i for i in items if i.kind != "tool_docs"]
        if not items:
            return None, []
        body = "\n\n".join(i.content for i in items)
        text = f"## {title}\n{body}"
        prov = [
            ProvenanceRef(kind="okf", ref_id=i.section_id or i.path or f"okf-{idx}", path=i.path, score=i.score)
            for idx, i in enumerate(items)
        ]
        return AssembledSection(name=kind, text=text, priority=0.9, tokens=_tokens(text)), prov

    def _tools(
        self, bundle: KnowledgeBundle, tool_prompt_block: str
    ) -> tuple[AssembledSection | None, list[ProvenanceRef]]:
        docs = [i for i in bundle.items if i.kind == "tool_docs"]
        parts: list[str] = []
        prov: list[ProvenanceRef] = []
        if tool_prompt_block:
            parts.append(tool_prompt_block)
        for i in docs:
            parts.append(i.content)
            prov.append(ProvenanceRef(kind="tool_docs", ref_id=i.path or "tools", score=i.score))
        if not parts:
            return None, []
        text = "## Tool Documentation (OKF)\n" + "\n\n".join(parts)
        return AssembledSection(name="tools", text=text, priority=0.7, tokens=_tokens(text)), prov
