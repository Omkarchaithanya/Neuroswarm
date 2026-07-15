"""RTG sensors — fill TelemetryFrame fields from live signals."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Mapping

from ..interfaces import ISensor
from ..models import SessionState, TelemetryFrame

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _char_entropy(text: str) -> float:
    if not text:
        return 1.0
    counts = Counter(text)
    n = len(text)
    h = 0.0
    for c in counts.values():
        p = c / n
        h -= p * math.log2(p)
    # Normalize roughly to [0, 1] for printable ASCII-ish
    return min(1.0, h / 6.0)


class EntropyMonitor(ISensor):
    name = "entropy"

    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        sample = frame.chunk_text or frame.accumulated_text[-512:]
        frame.token_entropy = _char_entropy(sample)
        state.entropy_history.append(frame.token_entropy)
        return frame


class ConfidenceEstimator(ISensor):
    name = "confidence"

    def __init__(self, *, uncertainty_phrases: list[str] | None = None) -> None:
        self.uncertainty_phrases = uncertainty_phrases or [
            "I don't know",
            "cannot",
            "uncertain",
        ]

    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        text = frame.accumulated_text or frame.chunk_text
        if not text.strip():
            frame.model_confidence = 0.0
            return frame
        score = 0.5 + min(0.4, len(text) / 8000.0)
        lowered = text.lower()
        for phrase in self.uncertainty_phrases:
            if phrase.lower() == "cannot":
                if "cannot" in lowered:
                    score -= 0.2
                    break
            elif phrase in text:
                score -= 0.2
                break
        # Blend tool + self-consistency
        score = 0.5 * score + 0.3 * frame.tool_confidence_top1 + 0.2 * frame.self_consistency_score
        frame.model_confidence = max(0.0, min(1.0, score))
        alpha = 0.35
        if state.confidence_history:
            prev = state.confidence_history[-1]
        else:
            prev = frame.model_confidence
        frame.confidence_ema = (1 - alpha) * prev + alpha * frame.model_confidence
        state.confidence_history.append(frame.confidence_ema)
        return frame


class ComplexityEstimator(ISensor):
    name = "complexity"

    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        text = frame.prompt_text or ""
        words = _WORD_RE.findall(text.lower())
        n = max(1, len(words))
        unique = len(set(words))
        lexical = unique / n
        length_term = min(1.0, n / 256.0)
        question_marks = text.count("?")
        codeish = 1.0 if any(t in text for t in ("```", "def ", "class ", "SELECT ")) else 0.0
        frame.complexity_score = max(
            0.05,
            min(1.0, 0.45 * length_term + 0.25 * lexical + 0.15 * min(1.0, question_marks / 3) + 0.15 * codeish),
        )
        frame.prompt_tokens = frame.prompt_tokens or max(1, n)
        return frame


class SelfConsistencyMonitor(ISensor):
    name = "self_consistency"

    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        texts = state.text_history[-3:] + ([frame.accumulated_text] if frame.accumulated_text else [])
        if len(texts) < 2:
            return frame
        # Jaccard over word sets of last answers / partials
        sets = [set(_WORD_RE.findall(t.lower())) for t in texts if t.strip()]
        if len(sets) < 2:
            return frame
        inter = len(sets[-1] & sets[-2])
        union = len(sets[-1] | sets[-2]) or 1
        j = inter / union
        frame.self_consistency_score = max(frame.self_consistency_score, j)
        return frame


class PlateauDetector(ISensor):
    name = "plateau"

    def __init__(self, *, epsilon: float = 0.02, windows: int = 3) -> None:
        self.epsilon = epsilon
        self.windows = windows

    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        hist = state.confidence_history
        if len(hist) < self.windows + 1:
            frame.plateau_score = 0.0
            return frame
        recent = hist[-(self.windows + 1) :]
        deltas = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
        if all(d < self.epsilon for d in deltas):
            frame.plateau_score = 1.0
        else:
            frame.plateau_score = max(0.0, 1.0 - (sum(deltas) / len(deltas)) / max(self.epsilon, 1e-6))
            frame.plateau_score = min(1.0, frame.plateau_score * 0.5)
        return frame


class KVPressureSensor(ISensor):
    name = "kv_pressure"

    def __init__(self, source: Any | None = None) -> None:
        self.source = source

    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        if self.source is None:
            return frame
        snap: Mapping[str, Any]
        if callable(getattr(self.source, "pressure_snapshot", None)):
            snap = dict(self.source.pressure_snapshot())
        elif callable(self.source):
            snap = dict(self.source())
        else:
            return frame
        frame.kv_pressure = float(snap.get("pressure", snap.get("kv_pressure", frame.kv_pressure)) or 0.0)
        frame.kv_hit_rate = float(snap.get("hit_rate", snap.get("kv_hit_rate", frame.kv_hit_rate)) or 0.0)
        frame.kv_storage_tier = int(snap.get("storage_tier", snap.get("kv_storage_tier", frame.kv_storage_tier)) or 1)
        frame.kv_migration_latency_ms = float(
            snap.get("migration_latency_ms", snap.get("kv_migration_latency_ms", frame.kv_migration_latency_ms))
            or 0.0
        )
        frame.memory_pressure = float(
            snap.get("memory_pressure", snap.get("ram_pressure", frame.memory_pressure)) or 0.0
        )
        frame.kv_dedup_ratio = float(snap.get("dedup_ratio", frame.kv_dedup_ratio) or 0.0)
        return frame


class SemanticSensor(ISensor):
    name = "semantic"

    def __init__(self, router: Any | None = None) -> None:
        self.router = router

    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        if self.router is None or not frame.prompt_text:
            # Approximate semantic entropy from tool conf
            c = frame.tool_confidence_top1
            frame.semantic_entropy = max(0.0, 1.0 - c)
            return frame
        try:
            tools = self.router.route(frame.prompt_text)
        except Exception:  # noqa: BLE001
            return frame
        if not tools:
            frame.tool_confidence_top1 = 0.0
            frame.semantic_entropy = 1.0
            return frame
        scores: list[float] = []
        names: list[str] = []
        for t in tools:
            score = float(getattr(t, "score", getattr(t, "confidence", 0.0)) or 0.0)
            name = str(getattr(t, "name", getattr(t, "id", "")) or "")
            scores.append(score)
            if name:
                names.append(name)
        if scores and max(scores) <= 1.0:
            frame.tool_confidence_top1 = max(scores)
            frame.tool_confidence_topk_mean = sum(scores) / len(scores)
        elif not frame.tool_confidence_top1 and tools:
            # Router without scores → high if tools returned
            frame.tool_confidence_top1 = 0.75
            frame.tool_confidence_topk_mean = 0.6
        frame.tool_names = names or frame.tool_names
        # Softmax-ish entropy proxy
        if scores:
            mx = max(scores) or 1.0
            probs = [math.exp(s / mx) for s in scores]
            z = sum(probs) or 1.0
            probs = [p / z for p in probs]
            h = -sum(p * math.log(p + 1e-12) for p in probs)
            frame.semantic_entropy = min(1.0, h / math.log(len(probs) + 1e-12))
        return frame


class LatencySLOSensor(ISensor):
    name = "latency_slo"

    def __init__(self, *, default_slo_ms: float = 4000.0) -> None:
        self.default_slo_ms = default_slo_ms

    def observe(self, frame: TelemetryFrame, state: SessionState) -> TelemetryFrame:
        spent = state.budget.latency_spent_ms
        slo = state.budget.latency_slo_ms or self.default_slo_ms
        frame.slo_remaining_ms = max(0.0, slo - spent)
        return frame
