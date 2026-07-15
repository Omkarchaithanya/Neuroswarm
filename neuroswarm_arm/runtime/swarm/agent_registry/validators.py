"""Validation rules for Agent records and registry writes."""

from __future__ import annotations

import re
from typing import Iterable

from .agent import Agent
from .exceptions import DuplicateAgentError, ValidationError

# Extensible allowlists — unknown values rejected unless allow_unknown=True
KNOWN_BACKENDS = frozenset(
    {
        "llama.cpp",
        "llamacpp",
        "vllm",
        "sglang",
        "executorch",
        "onnx",
        "torch",
        "mock",
        "cascade",
    }
)

KNOWN_QUANTIZATIONS = frozenset(
    {
        "q4_0",
        "q4_k_m",
        "q5_0",
        "q5_k_m",
        "q8_0",
        "fp8",
        "fp16",
        "bf16",
        "int8",
        "int4",
        "none",
    }
)

_VERSION_RE = re.compile(
    r"^\d+(\.\d+){0,2}([.-][A-Za-z0-9]+)*$"
)


def validate_version(version: str) -> None:
    if not version or not _VERSION_RE.match(version.strip()):
        raise ValidationError(f"invalid version: {version!r}", field="version")


def validate_agent(
    agent: Agent,
    *,
    allow_unknown_backend: bool = False,
    allow_unknown_quant: bool = False,
) -> None:
    if not agent.id or not str(agent.id).strip():
        raise ValidationError("id is required", field="id")
    if not agent.name or not str(agent.name).strip():
        raise ValidationError("name is required", field="name")
    if not agent.namespace or not str(agent.namespace).strip():
        raise ValidationError("namespace is required", field="namespace")
    validate_version(agent.version)

    if agent.metadata is None:
        raise ValidationError("metadata must be a dict", field="metadata")

    backends = agent.effective_backends()
    if not allow_unknown_backend:
        for b in backends:
            if b.lower() not in KNOWN_BACKENDS and b not in KNOWN_BACKENDS:
                # case-insensitive check
                if b.lower() not in {x.lower() for x in KNOWN_BACKENDS}:
                    raise ValidationError(f"invalid backend: {b}", field="supported_backends")

    quants = agent.effective_quants()
    if not allow_unknown_quant:
        known_lower = {q.lower() for q in KNOWN_QUANTIZATIONS}
        for q in quants:
            if q.lower() not in known_lower:
                raise ValidationError(
                    f"invalid quantization: {q}", field="supported_quantizations"
                )

    caps = agent.capabilities
    if caps.max_tokens < 1 or caps.max_context < 1:
        raise ValidationError("invalid capability limits", field="capabilities")

    # Preferred must be subset of supported when both present
    if caps.preferred_models and caps.supported_models:
        missing = set(caps.preferred_models) - set(caps.supported_models)
        if missing:
            raise ValidationError(
                f"preferred_models not in supported_models: {sorted(missing)}",
                field="preferred_models",
            )
    if caps.preferred_tools and caps.supported_tools:
        missing = set(caps.preferred_tools) - set(caps.supported_tools)
        if missing:
            raise ValidationError(
                f"preferred_tools not in supported_tools: {sorted(missing)}",
                field="preferred_tools",
            )


def check_duplicates(
    agent: Agent,
    *,
    existing_ids: Iterable[str],
    existing_names: Iterable[str],
    replace_id: str | None = None,
) -> None:
    ids = set(existing_ids)
    names = {n.lower() for n in existing_names}
    if agent.id in ids and agent.id != replace_id:
        raise DuplicateAgentError(f"duplicate agent id: {agent.id}", field="id")
    # name uniqueness among others
    for eid, ename in zip(existing_ids, existing_names):
        if eid == replace_id or eid == agent.id:
            continue
        if ename.lower() == agent.name.lower():
            raise DuplicateAgentError(
                f"duplicate agent name: {agent.name}", field="name"
            )
    # also catch if name collides and id is new
    if replace_id is None and agent.name.lower() in names and agent.id not in ids:
        # names set includes all; if id not registered yet but name is
        # need more precise: if any other agent has this name
        pass


def assert_not_frozen(agent: Agent) -> None:
    from .exceptions import FrozenAgentError

    if agent.frozen:
        raise FrozenAgentError(agent.id)
