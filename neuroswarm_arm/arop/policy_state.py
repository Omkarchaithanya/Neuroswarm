"""AROP policy state — load real knobs from ascr.yaml / RTG budgets, clamp safely."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from neuroswarm_arm.arop.exceptions import AropClampViolation, AropError
from neuroswarm_arm.runtime.armcascade.config.loader import load_ascr_config

LOG = logging.getLogger(__name__)

# Clamps intersect KNOB_CATALOG with tighter AROP bounds (plan).
CLAMP_DRAFT_K = (2, 8)
CLAMP_ACCEPT = (0.5, 0.95)
CLAMP_GOVERNOR = (256, 8192)

_MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_POLICY_PATH = _MODULE_DIR / "policy_state.yaml"
_RTG_BUDGETS = (
    Path(__file__).resolve().parents[1] / "runtime" / "rtg" / "config" / "budgets.yaml"
)


@dataclass(slots=True)
class PolicyState:
    cascade_draft_k: int
    tier_escalation_confidence: float  # maps to ASCR accept_threshold
    governor_thinking_cap: int
    # Recorded for honesty / seed only — v1 does NOT apply quant model-path changes.
    quant_tier2: str = "Q4_0"

    def clamp(self) -> PolicyState:
        """Return a clamped copy; raise if types are wrong."""
        try:
            draft = int(self.cascade_draft_k)
            conf = float(self.tier_escalation_confidence)
            cap = int(self.governor_thinking_cap)
        except (TypeError, ValueError) as exc:
            raise AropClampViolation(f"non-numeric policy field: {exc}") from exc
        draft_c = max(CLAMP_DRAFT_K[0], min(CLAMP_DRAFT_K[1], draft))
        conf_c = max(CLAMP_ACCEPT[0], min(CLAMP_ACCEPT[1], conf))
        cap_c = max(CLAMP_GOVERNOR[0], min(CLAMP_GOVERNOR[1], cap))
        return PolicyState(
            cascade_draft_k=draft_c,
            tier_escalation_confidence=conf_c,
            governor_thinking_cap=cap_c,
            quant_tier2=str(self.quant_tier2),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def copy(self) -> PolicyState:
        return PolicyState(**self.to_dict())


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise AropError("PyYAML required to load AROP policy state")
    if not path.is_file():
        raise AropError(f"policy/config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AropError(f"YAML root must be mapping: {path}")
    return dict(data)


def seed_from_live_config() -> PolicyState:
    """Read real current values from ascr.yaml + RTG budgets + compose convention.

    Raises if required keys cannot be read — never assumes fantasy defaults (5/0.85/2048).
    """
    ascr = load_ascr_config()
    defaults = ascr.get("defaults")
    if not isinstance(defaults, dict):
        raise AropError("ascr.yaml missing defaults mapping")
    if "draft_len" not in defaults or defaults["draft_len"] is None:
        raise AropError("ascr.yaml defaults.draft_len missing/null")
    if "accept_threshold" not in defaults or defaults["accept_threshold"] is None:
        raise AropError("ascr.yaml defaults.accept_threshold missing/null")

    budgets = _load_yaml(_RTG_BUDGETS)
    if "base_budget" not in budgets or budgets["base_budget"] is None:
        raise AropError(f"{_RTG_BUDGETS}: base_budget missing/null")

    # Axion compose pins Q4_0 for tier2; record only (no live apply in v1).
    quant = "Q4_0"

    state = PolicyState(
        cascade_draft_k=int(defaults["draft_len"]),
        tier_escalation_confidence=float(defaults["accept_threshold"]),
        governor_thinking_cap=int(budgets["base_budget"]),
        quant_tier2=quant,
    )
    return state.clamp()


def load_policy(path: Path | None = None) -> PolicyState:
    """Load policy_state.yaml, or seed from live config if file missing."""
    p = path or DEFAULT_POLICY_PATH
    if not p.is_file():
        LOG.info("policy file missing at %s — seeding from live config", p)
        return seed_from_live_config()
    data = _load_yaml(p)
    required = (
        "cascade_draft_k",
        "tier_escalation_confidence",
        "governor_thinking_cap",
    )
    for key in required:
        if key not in data or data[key] is None:
            raise AropError(f"{p}: required field {key!r} missing/null")
    return PolicyState(
        cascade_draft_k=int(data["cascade_draft_k"]),
        tier_escalation_confidence=float(data["tier_escalation_confidence"]),
        governor_thinking_cap=int(data["governor_thinking_cap"]),
        quant_tier2=str(data.get("quant_tier2") or "Q4_0"),
    ).clamp()


def save_policy(state: PolicyState, path: Path | None = None) -> Path:
    if yaml is None:
        raise AropError("PyYAML required to write AROP policy state")
    p = path or DEFAULT_POLICY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    clamped = state.clamp()
    text = yaml.safe_dump(clamped.to_dict(), default_flow_style=False, sort_keys=False)
    p.write_text(text, encoding="utf-8")
    return p


def write_gateway_env_overrides(state: PolicyState, env_path: Path) -> Path:
    """Write NSA_ASCR_* / RTG override file for gateway restart (no llama --draft)."""
    clamped = state.clamp()
    lines = [
        f"NSA_ASCR_DRAFT_LEN={clamped.cascade_draft_k}",
        f"NSA_ASCR_ACCEPT_THRESHOLD={clamped.tier_escalation_confidence}",
        f"NSA_RTG_BASE_BUDGET={clamped.governor_thinking_cap}",
        "",
    ]
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines), encoding="utf-8")
    return env_path
