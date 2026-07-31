"""Leviathan stochastic acceptance from target top-N logprobs."""

from __future__ import annotations

import math
import os
import random
import time
from dataclasses import dataclass
from typing import Any

from neuroswarm_arm.runtime.armcascade.confidence.engine import text_quality_score
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    ASCRInitContext,
    LogitsBundle,
    LogitsStep,
    LogitsTopEntry,
    Proposal,
    VerifyMode,
    VerifyRequest,
    VerifyResult,
    approx_tokens,
)
from neuroswarm_arm.runtime.armcascade.proposal.registry import register_verifier
from neuroswarm_arm.runtime.armcascade.verification.strategies import _BackendVerifierBase


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _parse_top_entry(entry: Any) -> LogitsTopEntry | None:
    if not isinstance(entry, dict):
        return None
    token = str(
        entry.get("token") or entry.get("text") or entry.get("content") or ""
    ).strip()
    if not token:
        return None
    lp = entry.get("logprob")
    logprob = float(lp) if isinstance(lp, (int, float)) else 0.0
    tid = entry.get("token_id")
    token_id = int(tid) if isinstance(tid, int) else None
    return LogitsTopEntry(token=token, logprob=logprob, token_id=token_id)


def _parse_step(entry: Any) -> LogitsStep | None:
    if isinstance(entry, str):
        token = entry.strip()
        if not token:
            return None
        return LogitsStep(token=token, logprob=0.0, top=[LogitsTopEntry(token=token, logprob=0.0)])
    if not isinstance(entry, dict):
        return None
    token = str(
        entry.get("token") or entry.get("text") or entry.get("content") or ""
    ).strip()
    lp = entry.get("logprob")
    logprob = float(lp) if isinstance(lp, (int, float)) else 0.0
    tid = entry.get("token_id")
    token_id = int(tid) if isinstance(tid, int) else None
    top_raw = entry.get("top_logprobs") or entry.get("top") or []
    top: list[LogitsTopEntry] = []
    if isinstance(top_raw, list):
        for item in top_raw:
            parsed = _parse_top_entry(item)
            if parsed is not None:
                top.append(parsed)
    if not top and token:
        top = [LogitsTopEntry(token=token, logprob=logprob, token_id=token_id)]
    return LogitsStep(token=token, logprob=logprob, token_id=token_id, top=top)


def parse_logits_bundle(
    raw: dict[str, Any],
    draft: Proposal,
    *,
    completion_text: str = "",
    top_n: int = 0,
) -> LogitsBundle:
    """Parse OpenAI logprobs.content or legacy completion_probabilities."""
    steps: list[LogitsStep] = []
    choices = raw.get("choices") or []
    if choices and isinstance(choices[0], dict):
        c0 = choices[0]
        logprobs = c0.get("logprobs")
        if isinstance(logprobs, dict):
            content = logprobs.get("content") or []
            if isinstance(content, list):
                for entry in content:
                    step = _parse_step(entry)
                    if step is not None:
                        steps.append(step)
        if not steps:
            legacy = c0.get("completion_probabilities") or c0.get("probs")
            if isinstance(legacy, list):
                for entry in legacy:
                    step = _parse_step(entry)
                    if step is not None:
                        steps.append(step)

    draft_tokens: list[str] = []
    draft_ids: list[int] = []
    draft_logps: list[float] = []
    draft_ranks: list[int] = []
    if draft.tokens:
        for tok in draft.tokens:
            draft_tokens.append(tok.text)
            draft_ids.append(tok.token_id if tok.token_id is not None else hash(tok.text))
            draft_logps.append(float(tok.logprob or 0.0))
            draft_ranks.append(int(tok.rank))
    else:
        words = draft.text.split() if draft.text.strip() else []
        draft_tokens = list(words)
        draft_ids = [hash(w) for w in words]
        draft_logps = [0.0 for _ in words]
        draft_ranks = [0 for _ in words]

    inferred_top_n = top_n
    if not inferred_top_n and steps:
        inferred_top_n = max(len(s.top) for s in steps)

    return LogitsBundle(
        steps=steps,
        draft_tokens=draft_tokens,
        draft_token_ids=draft_ids,
        draft_logprobs=draft_logps,
        draft_ranks=draft_ranks,
        top_n=int(inferred_top_n),
        completion_text=completion_text,
        raw=dict(raw),
    )


def _normalized_probs(top: list[LogitsTopEntry]) -> list[float]:
    if not top:
        return []
    logps = [t.logprob for t in top]
    max_lp = max(logps)
    exps = [math.exp(lp - max_lp) for lp in logps]
    total = sum(exps)
    if total <= 0:
        n = len(exps)
        return [1.0 / n for _ in exps]
    return [e / total for e in exps]


def _entropy_top_n(top: list[LogitsTopEntry]) -> float:
    probs = _normalized_probs(top)
    if not probs:
        return 1.0
    ent = 0.0
    for p in probs:
        if p > 0:
            ent -= p * math.log(p)
    return ent / max(1.0, math.log(len(probs)))


def _argmax_entry(top: list[LogitsTopEntry]) -> LogitsTopEntry | None:
    if not top:
        return None
    return max(top, key=lambda t: t.logprob)


def _find_in_top(
    top: list[LogitsTopEntry],
    token: str,
    token_id: int | None,
) -> LogitsTopEntry | None:
    for entry in top:
        if token_id is not None and entry.token_id is not None and entry.token_id == token_id:
            return entry
        if entry.token == token:
            return entry
    return None


def _cumulative_p(draft_logprob: float, rank: int, top_n: int) -> float:
    if rank < 0:
        rank = 0
    if rank >= top_n:
        return max(0.0, 1.0 - (rank + 1) / max(1, top_n + 1))
    mass = math.exp(min(0.0, draft_logprob))
    return min(1.0, mass + rank * 0.05)


@dataclass(slots=True)
class LeviathanAcceptResult:
    accepted_prefix_len: int = 0
    entropy: float = 0.5
    bonus_token: str = ""
    top_tau_used: bool = False


@dataclass(slots=True)
class PositionAcceptResult:
    """One-position streaming accept outcome."""

    accepted_token: str | None = None
    is_final: bool = False
    residual_or_bonus: str = ""
    top_tau_used: bool = False
    entropy: float = 0.5
    waiting: bool = False  # True when step not yet available


def accept_one_draft_position(
    bundle: LogitsBundle,
    draft: Any | None,
    position: int,
    *,
    greedy: bool = False,
    tau_floor: float = 0.0,
    rng: random.Random | None = None,
) -> PositionAcceptResult:
    """Accept/reject a single draft position as target logprobs arrive.

    Returns ``(accepted_token, is_final)`` semantics via :class:`PositionAcceptResult`:
    - accepted → ``accepted_token`` set; ``is_final`` only on last draft (bonus may follow)
    - rejected → ``accepted_token=None``, ``is_final=True``, residual in ``residual_or_bonus``
    - top-τ → accept draft then stop with target top-1 as ``residual_or_bonus``
    - bonus step (``position == k``) → ``residual_or_bonus`` = bonus, ``is_final=True``
    """
    rng = rng or random.Random()
    draft_tokens = list(bundle.draft_tokens)
    draft_ids = list(bundle.draft_token_ids)
    draft_logps = list(bundle.draft_logprobs)
    if draft is not None and not draft_tokens:
        if getattr(draft, "tokens", None):
            for tok in draft.tokens:
                draft_tokens.append(tok.text)
                draft_ids.append(
                    tok.token_id if tok.token_id is not None else hash(tok.text)
                )
                draft_logps.append(float(tok.logprob or 0.0))
        elif getattr(draft, "text", ""):
            words = draft.text.split() if str(draft.text).strip() else []
            draft_tokens = list(words)
            draft_ids = [hash(w) for w in words]
            draft_logps = [0.0 for _ in words]

    k = len(draft_tokens)
    if k == 0:
        return PositionAcceptResult(is_final=True, entropy=1.0)

    # Bonus beyond fully accepted draft.
    if position == k:
        if position >= len(bundle.steps):
            return PositionAcceptResult(waiting=True, entropy=0.5)
        bonus_step = bundle.steps[position]
        top1 = _argmax_entry(bonus_step.top)
        bonus = top1.token if top1 is not None else (bonus_step.token or "")
        return PositionAcceptResult(
            is_final=True,
            residual_or_bonus=bonus,
            entropy=_entropy_top_n(bonus_step.top),
        )

    if position < 0 or position > k:
        return PositionAcceptResult(is_final=True, entropy=1.0)

    if position >= len(bundle.steps):
        return PositionAcceptResult(waiting=True, entropy=0.5)

    step = bundle.steps[position]
    draft_token = draft_tokens[position]
    draft_id = draft_ids[position] if position < len(draft_ids) else None
    draft_p = draft_logps[position] if position < len(draft_logps) else 0.0
    last_draft = position == k - 1
    ent = _entropy_top_n(step.top)

    target_entry = _find_in_top(step.top, draft_token, draft_id)

    if target_entry is None:
        # Top-τ truncation: accept draft if p_draft >= tau, then stop with top-1 bonus.
        p_draft = math.exp(min(0.0, float(draft_p)))
        if tau_floor > 0 and p_draft >= tau_floor:
            top1 = _argmax_entry(step.top)
            return PositionAcceptResult(
                accepted_token=draft_token,
                is_final=True,
                residual_or_bonus=top1.token if top1 is not None else "",
                top_tau_used=True,
                entropy=ent,
            )
        residual = ""
        top1 = _argmax_entry(step.top)
        if top1 is not None:
            residual = top1.token
        elif step.token:
            residual = step.token
        return PositionAcceptResult(
            accepted_token=None,
            is_final=True,
            residual_or_bonus=residual,
            entropy=ent,
        )

    q = target_entry.logprob
    ratio = min(1.0, math.exp(q - draft_p))

    if greedy:
        argmax = _argmax_entry(step.top)
        if argmax is None:
            return PositionAcceptResult(
                accepted_token=None,
                is_final=True,
                residual_or_bonus=step.token or "",
                entropy=ent,
            )
        match = False
        if draft_id is not None and argmax.token_id is not None:
            match = draft_id == argmax.token_id
        if not match:
            match = draft_token == argmax.token
        if match:
            return PositionAcceptResult(
                accepted_token=draft_token,
                is_final=last_draft,
                entropy=ent,
            )
        return PositionAcceptResult(
            accepted_token=None,
            is_final=True,
            residual_or_bonus=argmax.token,
            entropy=ent,
        )

    if rng.random() < ratio:
        return PositionAcceptResult(
            accepted_token=draft_token,
            is_final=last_draft,
            entropy=ent,
        )
    residual = ""
    top1 = _argmax_entry(step.top)
    if top1 is not None:
        residual = top1.token
    elif step.token:
        residual = step.token
    return PositionAcceptResult(
        accepted_token=None,
        is_final=True,
        residual_or_bonus=residual,
        entropy=ent,
    )


def leviathan_accept(
    bundle: LogitsBundle,
    *,
    greedy: bool = False,
    tau_floor: float = 0.0,
    rng: random.Random | None = None,
) -> LeviathanAcceptResult:
    """Leviathan acceptance: min(1, exp(q-p)) stochastic or argmax greedy."""
    rng = rng or random.Random()
    k = len(bundle.draft_tokens)
    if k == 0 or not bundle.steps:
        return LeviathanAcceptResult(accepted_prefix_len=0, entropy=1.0)

    accepted = 0
    top_tau_used = False
    reject_entropy = 0.5
    tau_bonus = ""

    for i in range(k):
        pos = accept_one_draft_position(
            bundle,
            None,
            i,
            greedy=greedy,
            tau_floor=tau_floor,
            rng=rng,
        )
        if pos.waiting:
            reject_entropy = pos.entropy
            break
        if pos.top_tau_used:
            top_tau_used = True
            if pos.accepted_token is not None:
                accepted += 1
            tau_bonus = pos.residual_or_bonus
            reject_entropy = pos.entropy
            break
        if pos.accepted_token is not None:
            accepted += 1
            reject_entropy = pos.entropy
            continue
        reject_entropy = pos.entropy
        break

    bonus = tau_bonus
    if not bonus and accepted >= k and len(bundle.steps) > k:
        bonus_pos = accept_one_draft_position(
            bundle,
            None,
            k,
            greedy=greedy,
            tau_floor=tau_floor,
            rng=rng,
        )
        if not bonus_pos.waiting:
            bonus = bonus_pos.residual_or_bonus

    return LeviathanAcceptResult(
        accepted_prefix_len=accepted,
        entropy=reject_entropy if accepted < k else _entropy_top_n(
            bundle.steps[min(accepted, len(bundle.steps) - 1)].top
        ),
        bonus_token=bonus,
        top_tau_used=top_tau_used,
    )


@register_verifier("logits")
class LogitsAcceptanceVerifier(_BackendVerifierBase):
    """Target-forward Leviathan acceptance using top-N logprobs."""

    name = "logits"

    def __init__(self, backend_name: str = "tier2", tau_floor: float = 0.0) -> None:
        super().__init__(backend_name=backend_name)
        self._tau_floor = tau_floor
        self._top_n = 5
        self._enabled = True

    async def initialize(self, ctx: ASCRInitContext) -> None:
        await super().initialize(ctx)
        cfg = dict(ctx.config or {})
        strategies = dict(cfg.get("strategies") or {})
        logits_cfg = dict(strategies.get("logits") or {})
        self._enabled = bool(logits_cfg.get("enabled", True))
        if os.getenv("NSA_ASCR_LOGITS_ENABLED") is not None:
            self._enabled = _env_bool("NSA_ASCR_LOGITS_ENABLED", self._enabled)
        self._tau_floor = float(logits_cfg.get("tau_floor", self._tau_floor))
        self._tau_floor = _env_float("NSA_ASCR_TAU_FLOOR", self._tau_floor)
        self._top_n = _env_int(
            "NSA_ASCR_LOGITS_TOP_N",
            int(logits_cfg.get("top_n", _env_int("NSA_LLAMA_N_PROBS_DEFAULT", 5))),
        )
        if int(os.getenv("NSA_LLAMA_N_PROBS", "0") or "0") <= 0:
            os.environ["NSA_LLAMA_N_PROBS"] = str(self._top_n)

    async def verify(self, draft: Proposal, req: VerifyRequest) -> VerifyResult:
        if not self._enabled:
            raise NotImplementedError("logits verifier disabled (strategies.logits.enabled=false)")

        t0 = time.monotonic()
        k = max(1, draft.draft_len or approx_tokens(draft.text))
        result = await self._generate(req, max_tokens=k + 1, top_logprobs=self._top_n)
        raw = dict(result.raw) if result.raw else {}
        text = result.text or ""
        bundle = parse_logits_bundle(
            raw,
            draft,
            completion_text=text,
            top_n=self._top_n,
        )
        greedy = float(req.temperature) == 0.0
        accept = leviathan_accept(
            bundle,
            greedy=greedy,
            tau_floor=self._tau_floor,
        )
        prefix_len = accept.accepted_prefix_len
        agreement = prefix_len / max(1, k)
        quality = text_quality_score(text, self._quality_cfg)
        elapsed = (time.monotonic() - t0) * 1000.0

        return VerifyResult(
            accepted_prefix_len=prefix_len,
            rejected=prefix_len == 0,
            agreement=agreement,
            entropy=accept.entropy,
            text=text,
            mode=VerifyMode.LOGITS,
            logits_available=True,
            quality_score=quality,
            latency_ms=result.latency_ms or elapsed,
            backend=result.backend or self.backend_name,
            model=result.model,
            tier_used=req.verifier_tier,
            bonus_token=accept.bonus_token,
            metrics={
                "draft_len": float(k),
                "prefix_len": float(prefix_len),
                "agreement": agreement,
                "accept_mode": 2.0,
                "top_tau_used": 1.0 if accept.top_tau_used else 0.0,
            },
            raw=raw,
        )
