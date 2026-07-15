"""Policy engine — agent/role → EnvelopeTemplate."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .config import BudgetRuntimeConfig
from .schemas import EnvelopeTemplate, FailurePolicy


# Built-in role templates (overridable via OKF / plugins / env)
_BUILTIN_ROLES: dict[str, dict[str, Any]] = {
    "research": {
        "cost_usd": 0.10,
        "reasoning_tokens": 6000,
        "prompt_tokens": 12_000,
        "completion_tokens": 4096,
        "tool_calls": 16,
        "kv_bytes": 4 * 1024**3,
        "preferred_model_tier": 3,
        "min_confidence": 0.6,
    },
    "research_analyst": {
        "cost_usd": 0.10,
        "reasoning_tokens": 6000,
        "prompt_tokens": 12_000,
        "preferred_model_tier": 3,
    },
    "chat": {
        "cost_usd": 0.01,
        "reasoning_tokens": 256,
        "prompt_tokens": 4096,
        "completion_tokens": 1024,
        "tool_calls": 4,
        "kv_bytes": 512 * 1024**2,
        "preferred_model_tier": 1,
    },
    "tool_call": {
        "cost_usd": 0.02,
        "reasoning_tokens": 128,
        "tool_calls": 8,
        "preferred_model_tier": 2,
    },
    "summarization": {
        "cost_usd": 0.005,
        "reasoning_tokens": 64,
        "prompt_tokens": 8192,
        "completion_tokens": 1024,
        "memory_bytes": 2 * 1024**3,
        "tool_calls": 0,
        "preferred_model_tier": 1,
        "preferred_quantization": "q4",
    },
    "coding": {
        "cost_usd": 0.05,
        "reasoning_tokens": 2048,
        "tool_calls": 12,
        "preferred_model_tier": 2,
    },
    "planner": {
        "cost_usd": 0.05,
        "reasoning_tokens": 3000,
        "preferred_model_tier": 2,
    },
    "default": {},
}


class DefaultPolicyCompiler:
    def __init__(self, cfg: BudgetRuntimeConfig, *, okf_root: Path | None = None) -> None:
        self.cfg = cfg
        self.okf_root = okf_root or Path("okf")

    def compile(
        self,
        *,
        agent_role: str,
        tenant_id: str = "",
        overrides: Mapping[str, Any] | None = None,
    ) -> EnvelopeTemplate:
        del tenant_id
        role = (agent_role or "default").strip().lower().replace("-", "_")
        base = dict(_BUILTIN_ROLES.get("default", {}))
        # fuzzy match
        matched = _BUILTIN_ROLES.get(role)
        if matched is None:
            for key, val in _BUILTIN_ROLES.items():
                if key in role or role in key:
                    matched = val
                    break
        if matched:
            base.update(matched)
        okf = self._load_okf_cost_policy()
        if okf:
            # OKF supplies institutional defaults when role didn't set cost
            if "cost_usd" not in base and "cost_usd" in okf:
                base["cost_usd"] = okf["cost_usd"]
            if "prompt_tokens" not in base and "prompt_tokens" in okf:
                base["prompt_tokens"] = okf["prompt_tokens"]
        if overrides:
            base.update({k: v for k, v in overrides.items() if v is not None})
        return EnvelopeTemplate(
            agent_role=agent_role or "default",
            cost_usd=base.get("cost_usd"),
            latency_ms=base.get("latency_ms"),
            memory_bytes=base.get("memory_bytes"),
            energy_joules=base.get("energy_joules"),
            prompt_tokens=base.get("prompt_tokens"),
            completion_tokens=base.get("completion_tokens"),
            reasoning_tokens=base.get("reasoning_tokens"),
            kv_bytes=base.get("kv_bytes"),
            tool_calls=base.get("tool_calls"),
            cpu_seconds=base.get("cpu_seconds"),
            streaming_ms=base.get("streaming_ms"),
            retries=base.get("retries"),
            concurrency=base.get("concurrency"),
            max_context_length=base.get("max_context_length"),
            max_batch_size=base.get("max_batch_size"),
            priority=base.get("priority"),
            min_confidence=base.get("min_confidence"),
            preferred_quantization=base.get("preferred_quantization"),
            preferred_backend=base.get("preferred_backend"),
            preferred_model_tier=base.get("preferred_model_tier"),
            failure_policy=FailurePolicy(
                str(base.get("failure_policy", FailurePolicy.DEGRADE.value))
            ),
            metadata={"source": "policy_engine", "role": role},
        )

    def _load_okf_cost_policy(self) -> dict[str, Any]:
        path = self.okf_root / "policies" / "cost-budget.md"
        if not path.is_file():
            return {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        out: dict[str, Any] = {}
        m = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", text)
        if m:
            out["cost_usd"] = float(m.group(1))
        m2 = re.search(r"`?(\d+)`?\s*tokens", text, re.IGNORECASE)
        if m2:
            out["prompt_tokens"] = int(m2.group(1))
        return out


class PolicyEngine:
    def __init__(self, compiler: DefaultPolicyCompiler) -> None:
        self.compiler = compiler

    def compile(
        self,
        *,
        agent_role: str,
        tenant_id: str = "",
        overrides: Mapping[str, Any] | None = None,
    ) -> EnvelopeTemplate:
        return self.compiler.compile(
            agent_role=agent_role, tenant_id=tenant_id, overrides=overrides
        )
