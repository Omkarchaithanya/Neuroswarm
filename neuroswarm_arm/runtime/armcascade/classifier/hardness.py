"""Map prompt hardness (basic / medium / advanced) to cascade start tier."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping

from neuroswarm_arm.runtime.armcascade.interfaces.types import Classification, TaskKind

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.armcascade.classifier.heuristic import HeuristicRequestClassifier
    from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan, InferenceRequest

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")

_DEFAULT_HARDNESS_ROUTING: dict[str, Any] = {
    "enabled": True,
    "bands": {
        "basic": {"max_complexity": 0.40, "tier": 1},
        "medium": {"max_complexity": 0.65, "tier": 2},
        "advanced": {"tier": 3},
    },
    "length_bump": {
        "medium_min_tokens": 256,
        "advanced_min_tokens": 512,
    },
}

_BASIC_KINDS = {TaskKind.FACTUAL, TaskKind.CHAT, TaskKind.JSON, TaskKind.STREAMING}
_MEDIUM_KINDS = {TaskKind.TOOL_USE, TaskKind.RAG, TaskKind.JSON}
_ADVANCED_KINDS = {
    TaskKind.REASONING,
    TaskKind.CODE,
    TaskKind.PLANNING,
    TaskKind.MULTI_AGENT,
}


class HardnessBand(str, Enum):
    BASIC = "basic"
    MEDIUM = "medium"
    ADVANCED = "advanced"


@dataclass(slots=True)
class HardnessClassification:
    band: HardnessBand
    start_tier: int
    complexity: float
    confidence: float
    signals: dict[str, float] = field(default_factory=dict)


def _lexical_complexity(text: str) -> float:
    words = _WORD_RE.findall(text.lower())
    n = max(1, len(words))
    unique = len(set(words))
    lexical = unique / n
    length_term = min(1.0, n / 256.0)
    question_marks = text.count("?")
    codeish = 1.0 if any(t in text for t in ("```", "def ", "class ", "SELECT ")) else 0.0
    return max(
        0.05,
        min(
            1.0,
            0.45 * length_term
            + 0.25 * lexical
            + 0.15 * min(1.0, question_marks / 3)
            + 0.15 * codeish,
        ),
    )


def _band_from_complexity(
    complexity: float,
    task_kind: TaskKind,
    cfg: Mapping[str, Any],
) -> HardnessBand:
    bands = dict(cfg.get("bands") or {})
    basic_max = float((bands.get("basic") or {}).get("max_complexity", 0.40))
    medium_max = float((bands.get("medium") or {}).get("max_complexity", 0.65))

    if task_kind in _ADVANCED_KINDS or complexity >= medium_max:
        return HardnessBand.ADVANCED
    if task_kind in _MEDIUM_KINDS or complexity >= basic_max:
        return HardnessBand.MEDIUM
    if task_kind in _BASIC_KINDS and complexity < basic_max:
        return HardnessBand.BASIC
    if complexity < basic_max:
        return HardnessBand.BASIC
    if complexity < medium_max:
        return HardnessBand.MEDIUM
    return HardnessBand.ADVANCED


def _tier_for_band(band: HardnessBand, cfg: Mapping[str, Any]) -> int:
    bands = dict(cfg.get("bands") or {})
    if band is HardnessBand.BASIC:
        return int((bands.get("basic") or {}).get("tier", 1))
    if band is HardnessBand.MEDIUM:
        return int((bands.get("medium") or {}).get("tier", 2))
    return int((bands.get("advanced") or {}).get("tier", 3))


def _length_bump_tier(prompt_tokens: int, cfg: Mapping[str, Any]) -> int:
    bump = dict(cfg.get("length_bump") or {})
    medium_min = int(bump.get("medium_min_tokens", 256))
    advanced_min = int(bump.get("advanced_min_tokens", 512))
    if prompt_tokens >= advanced_min:
        return 3
    if prompt_tokens >= medium_min:
        return 2
    return 1


class HardnessTierMapper:
    """Classify prompt hardness and pick cascade start tier."""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        classifier: HeuristicRequestClassifier | None = None,
    ) -> None:
        raw = dict(config or {})
        merged = dict(_DEFAULT_HARDNESS_ROUTING)
        merged.update({k: v for k, v in raw.items() if k != "bands" and k != "length_bump"})
        if "bands" in raw:
            merged["bands"] = {**_DEFAULT_HARDNESS_ROUTING["bands"], **dict(raw["bands"])}
        if "length_bump" in raw:
            merged["length_bump"] = {
                **_DEFAULT_HARDNESS_ROUTING["length_bump"],
                **dict(raw["length_bump"]),
            }
        self.config = merged
        self._classifier = classifier

    def _get_classifier(self) -> HeuristicRequestClassifier:
        if self._classifier is None:
            from neuroswarm_arm.runtime.armcascade.classifier.heuristic import (
                HeuristicRequestClassifier,
            )

            self._classifier = HeuristicRequestClassifier()
        return self._classifier

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def classify(
        self,
        req: InferenceRequest,
        plan: ExecutionPlan | None = None,
        *,
        classification: Classification | None = None,
    ) -> HardnessClassification:
        clf = classification or self._get_classifier().classify(req, plan)
        text = req.prompt_text or ""
        prompt_tokens = max(1, len(text.split()))
        lexical = _lexical_complexity(text)
        blended = max(clf.complexity, lexical * 0.35 + clf.complexity * 0.65)

        text_lower = text.lower()
        style_only = any(
            phrase in text_lower
            for phrase in (
                "in an advanced way",
                "advanced way",
                "in depth",
                "in detail",
                "comprehensive",
                "thorough",
            )
        )
        explain_only = any(
            phrase in text_lower
            for phrase in ("explain", "describe", "tell me about", "overview of")
        )
        if style_only and explain_only and clf.task_kind not in _ADVANCED_KINDS:
            blended = min(blended, 0.38)

        band = _band_from_complexity(blended, clf.task_kind, self.config)
        start_tier = _tier_for_band(band, self.config)
        bump_tier = _length_bump_tier(prompt_tokens, self.config)
        start_tier = max(start_tier, bump_tier)

        if start_tier >= 3:
            band = HardnessBand.ADVANCED
        elif start_tier >= 2 and band is HardnessBand.BASIC:
            band = HardnessBand.MEDIUM

        confidence = 0.55 + min(0.35, abs(blended - 0.5))
        if clf.task_kind in _ADVANCED_KINDS or clf.task_kind in _BASIC_KINDS:
            confidence = min(1.0, confidence + 0.1)

        signals = {
            "classifier_complexity": float(clf.complexity),
            "lexical_complexity": float(lexical),
            "blended_complexity": float(blended),
            "prompt_tokens": float(prompt_tokens),
            "length_bump_tier": float(bump_tier),
            "task_kind": float(hash(clf.task_kind.value) % 1000),
        }
        signals.update(clf.signals)

        #region agent log
        try:
            import json
            import time
            from pathlib import Path

            _log_path = Path(__file__).resolve().parents[4] / "debug-bfa34a.log"
            _log_path.parent.mkdir(parents=True, exist_ok=True)
            with _log_path.open("a", encoding="utf-8") as _fh:
                _fh.write(
                    json.dumps(
                        {
                            "sessionId": "bfa34a",
                            "hypothesisId": "H4",
                            "location": "hardness.py:classify",
                            "message": "hardness_result",
                            "data": {
                                "band": band.value,
                                "start_tier": max(1, min(3, start_tier)),
                                "blended": blended,
                                "style_only": style_only,
                                "explain_only": explain_only,
                                "task_kind": clf.task_kind.value,
                            },
                            "timestamp": int(time.time() * 1000),
                            "runId": "smart-cascade",
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        #endregion

        return HardnessClassification(
            band=band,
            start_tier=max(1, min(3, start_tier)),
            complexity=blended,
            confidence=confidence,
            signals=signals,
        )


def hardness_routing_config(cascade_cfg: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract hardness_routing block from cascade.yaml dict."""
    raw = dict(cascade_cfg or {}).get("hardness_routing") or {}
    if not raw:
        return dict(_DEFAULT_HARDNESS_ROUTING)
    merged = dict(_DEFAULT_HARDNESS_ROUTING)
    merged.update({k: v for k, v in raw.items() if k not in {"bands", "length_bump"}})
    if "bands" in raw:
        merged["bands"] = {**_DEFAULT_HARDNESS_ROUTING["bands"], **dict(raw["bands"])}
    if "length_bump" in raw:
        merged["length_bump"] = {
            **_DEFAULT_HARDNESS_ROUTING["length_bump"],
            **dict(raw["length_bump"]),
        }
    return merged
