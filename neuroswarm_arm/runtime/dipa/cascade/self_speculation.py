"""N-gram self-speculation draft helper."""

from __future__ import annotations

from dataclasses import dataclass

from .cascade_policy import SpeculationPolicy


@dataclass
class SelfSpeculationEngine:
    """Cheap n-gram draft suffix for speculative decoding hints.

    Does not call a backend; produces an optional draft continuation from the
    trailing token n-gram of *text*. Disabled engines always return ``None``.
    """

    enabled: bool = False
    ngram_size: int = 24
    draft_min: int = 12
    draft_max: int = 48

    @classmethod
    def from_policy(cls, policy: SpeculationPolicy) -> SelfSpeculationEngine:
        return cls(
            enabled=bool(policy.enabled and policy.self_speculation),
            ngram_size=max(1, int(policy.ngram_size)),
            draft_min=max(0, int(policy.draft_min)),
            draft_max=max(0, int(policy.draft_max)),
        )

    def draft_suffix(self, text: str) -> str | None:
        """Return an optional draft continuation derived from trailing n-grams."""
        if not self.enabled:
            return None
        words = text.split()
        if len(words) < self.draft_min:
            return None

        n = min(self.ngram_size, len(words))
        seed = words[-n:]
        # Repeat the trailing n-gram as a soft draft, clipped to draft_max tokens.
        draft_tokens: list[str] = []
        while len(draft_tokens) < self.draft_max:
            remaining = self.draft_max - len(draft_tokens)
            draft_tokens.extend(seed[:remaining])
            if remaining <= len(seed):
                break
        if len(draft_tokens) < self.draft_min:
            return None
        return " ".join(draft_tokens)
