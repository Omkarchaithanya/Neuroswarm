from __future__ import annotations

import re
from dataclasses import dataclass, field


INTENT_HINTS = {
    "agent": ["agent", "role", "persona"],
    "tool": ["tool", "mcp", "api", "github", "postgres", "s3", "slack"],
    "policy": ["policy", "budget", "cost", "security", "permission"],
    "playbook": ["playbook", "runbook", "how to", "procedure"],
    "metric": ["metric", "latency", "throughput", "hit rate"],
}


@dataclass
class Intent:
    kinds: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


def detect_intent(text: str) -> Intent:
    lower = text.lower()
    kinds: list[str] = []
    for kind, hints in INTENT_HINTS.items():
        if any(h in lower for h in hints):
            kinds.append(kind)
    terms = [t for t in re.findall(r"[a-zA-Z0-9_\-]{3,}", lower) if t not in {"the", "and", "for", "with"}]
    tags = list(kinds)
    return Intent(kinds=kinds or ["concept"], tags=tags, terms=terms)
