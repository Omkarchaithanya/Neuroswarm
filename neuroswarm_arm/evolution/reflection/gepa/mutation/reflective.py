"""
Reflective mutation — LLM (or mock) proposes improved text components.

Official concept: reflective mutation proposer (GEPA engine iteration);
teacher LM reads reflective dataset and emits new component texts.

ArmCascade/AROP: mutates prompts/policies only; never hardware knobs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from neuroswarm_arm.evolution.reflection.gepa.asi.schema import ActionableSideInformation
from neuroswarm_arm.evolution.reflection.gepa.candidate.models import (
    MutationEvent,
    TextCandidate,
    validate_text_components,
)


class ReflectionLM(ABC):
    """Teacher LLM port for proposing new component texts."""

    @abstractmethod
    def propose(
        self,
        candidate: Mapping[str, str],
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        raise NotImplementedError


class MockReflectionLM(ReflectionLM):
    """Deterministic teacher for CI — appends lesson tags from ASI feedback."""

    def propose(
        self,
        candidate: Mapping[str, str],
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        lessons: list[str] = []
        for comp, rows in reflective_dataset.items():
            for row in rows[:3]:
                fb = str(row.get("Feedback", ""))[:200]
                if fb:
                    lessons.append(fb)
        lesson_block = " | ".join(lessons)[:400] or "stabilize quality and reduce latency"
        out = dict(candidate)
        for comp in components_to_update:
            base = out.get(comp, "")
            tag = f"\n\n[GEPA lesson]: {lesson_block}"
            if "[GEPA lesson]" in base:
                # Refresh lesson line
                head = base.split("[GEPA lesson]")[0].rstrip()
                out[comp] = f"{head}\n\n[GEPA lesson]: {lesson_block}"
            else:
                out[comp] = f"{base}{tag}" if base else f"You are a careful assistant.\n[GEPA lesson]: {lesson_block}"
        return validate_text_components(out)


class HttpReflectionLM(ReflectionLM):
    """Teacher LM via OpenAI-compatible ``/v1/chat/completions`` (llama-server / tier)."""

    def __init__(
        self,
        base_url: str,
        *,
        model: str = "default",
        timeout_s: float = 60.0,
        max_tokens: int = 512,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        # http | mock_fallback — set after each propose() for deploy honesty.
        self.last_teacher: str = "http"

    def propose(
        self,
        candidate: Mapping[str, str],
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        import json
        import urllib.error
        import urllib.request

        lessons: list[str] = []
        for _comp, rows in reflective_dataset.items():
            for row in rows[:5]:
                fb = str(row.get("Feedback") or row.get("feedback") or "")[:300]
                if fb:
                    lessons.append(fb)
        lesson_block = " | ".join(lessons)[:800] or "improve clarity and reduce latency"
        out = dict(candidate)
        any_http = False
        any_fallback = False
        for comp in components_to_update:
            base = out.get(comp, "You are a helpful assistant.")
            user = (
                f"Improve the following component '{comp}' for an ARM agent runtime.\n"
                f"Lessons from telemetry:\n{lesson_block}\n\n"
                f"Current text:\n{base}\n\n"
                "Return ONLY the improved component text, no markdown fences. "
                "Include the token GEPA-HTTP-TEACHER once if you rewrite successfully."
            )
            body = json.dumps(
                {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You rewrite system prompts and policies. Output the new text only.",
                        },
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": 0.3,
                }
            ).encode("utf-8")
            url = f"{self.base_url}/chat/completions"
            if self.base_url.rstrip("/").endswith("chat/completions"):
                url = self.base_url
            elif not self.base_url.rstrip("/").endswith("/v1"):
                url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
            else:
                url = f"{self.base_url.rstrip('/')}/chat/completions"
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                text = (
                    ((raw.get("choices") or [{}])[0].get("message") or {}).get("content")
                    or ""
                ).strip()
                if text and "[GEPA lesson]:" not in text:
                    out[comp] = text
                    any_http = True
                else:
                    out[comp] = f"{base}\n\n[GEPA lesson]: {lesson_block}"
                    any_fallback = True
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
                # Fall back to mock-style tag so evolution still progresses.
                out[comp] = f"{base}\n\n[GEPA lesson]: {lesson_block}"
                any_fallback = True
        if any_http and not any_fallback:
            self.last_teacher = "http"
        elif any_http and any_fallback:
            self.last_teacher = "http_partial"
        else:
            self.last_teacher = "mock_fallback"
        return validate_text_components(out)


def build_reflection_lm(spec: str | None = None) -> ReflectionLM:
    """Build teacher LM from ``NSA_AROP_GEPA_LM`` (mock | http URL)."""
    import os

    raw = (spec if spec is not None else os.getenv("NSA_AROP_GEPA_LM", "mock")).strip()
    if not raw or raw.lower() in {"mock", "none", "0", "off"}:
        return MockReflectionLM()
    model = os.getenv("NSA_AROP_GEPA_LM_MODEL", "default")
    return HttpReflectionLM(raw, model=model)


class ReflectiveMutationEngine:
    """Produce a child TextCandidate from parent + ASI via ReflectionLM."""

    def __init__(self, lm: ReflectionLM | None = None) -> None:
        self.lm = lm or MockReflectionLM()
        self._version = 0

    def mutate(
        self,
        parent: TextCandidate,
        *,
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str] | None = None,
        asi: ActionableSideInformation | None = None,
    ) -> TextCandidate:
        comps = list(components_to_update or list(parent.components.keys()) or ["system_prompt"])
        if not comps:
            comps = ["system_prompt"]
        # Ensure keys exist
        seed = dict(parent.components)
        for c in comps:
            seed.setdefault(c, "You are a helpful assistant.")
        proposed = self.lm.propose(seed, reflective_dataset, comps)
        self._version += 1
        rationale = asi.feedback_text()[:300] if asi else "reflective_mutation"
        event = MutationEvent(
            at=datetime.now(timezone.utc),
            parent_id=parent.id,
            rationale=rationale,
            components_updated=tuple(comps),
        )
        teacher = getattr(self.lm, "last_teacher", None)
        if teacher is None:
            teacher = "mock" if type(self.lm).__name__ == "MockReflectionLM" else "unknown"
        return TextCandidate.create(
            proposed,
            version=f"v{self._version}",
            parent_ids=(parent.id,),
            metadata={"strategy": "reflective_mutation", "teacher": teacher},
            mutation_history=parent.mutation_history + (event,),
            merge_history=parent.merge_history,
        )
