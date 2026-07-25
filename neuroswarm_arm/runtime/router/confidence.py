"""Confidence estimation for routed tools."""

from __future__ import annotations

from .models import ScoredTool


def _tool_family(tool_id: str) -> str:
    tid = str(tool_id or "")
    if "." in tid:
        return tid.split(".", 1)[0].lower()
    return tid.lower()


def estimate_confidence(tools: list[ScoredTool]) -> float:
    """Blend absolute score, margin, and same-family consensus.

    FastEmbed/BGE cosine scores for sibling tools (e.g. s3.put vs s3.get) often
    sit in a narrow band with tiny margins — raw margin confidence then never
    clears a high-conf gate even on clear domain intents. Family consensus recovers
    that signal for thinking-cap / schema-injection decisions.
    """
    if not tools:
        return 0.0
    top = float(tools[0].score)
    if len(tools) == 1:
        conf = min(1.0, max(0.0, top))
        tools[0].confidence = conf
        return conf

    second = float(tools[1].score)
    margin = max(0.0, top - second)
    # Mild affine lift for typical BGE cosine bands (~0.3–0.7 → stretch toward 1).
    abs_score = min(1.0, max(0.0, (top - 0.15) / 0.70))
    conf = 0.55 * abs_score + 0.25 * min(1.0, margin * 4.0)

    families = [_tool_family(getattr(t.tool, "id", "")) for t in tools[:3]]
    if families and families[0] and all(f == families[0] for f in families if f):
        conf += 0.25
    elif families and sum(1 for f in families if f == families[0]) >= 2:
        conf += 0.15

    conf = min(1.0, max(0.0, conf))
    tools[0].confidence = conf
    for tool in tools[1:]:
        tool.confidence = min(conf, max(0.0, float(tool.score)))
    return conf


def below_threshold(confidence: float, threshold: float) -> bool:
    return confidence < threshold
