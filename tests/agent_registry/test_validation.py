"""Validation tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.agent_registry import Agent, ValidationError
from neuroswarm_arm.runtime.swarm.agent_registry.capability import AgentCapability
from neuroswarm_arm.runtime.swarm.agent_registry.validators import validate_agent


def test_invalid_backend():
    a = Agent(
        name="bad",
        capabilities=AgentCapability(supported_backends=["not-a-backend"]),
    )
    with pytest.raises(ValidationError, match="invalid backend"):
        validate_agent(a)


def test_invalid_quant():
    a = Agent(
        name="bad",
        capabilities=AgentCapability(
            supported_backends=["llama.cpp"],
            supported_quantizations=["magic_quant"],
        ),
    )
    with pytest.raises(ValidationError, match="invalid quantization"):
        validate_agent(a)


def test_invalid_version():
    a = Agent(
        name="bad",
        version="not-semver!!!",
        capabilities=AgentCapability(
            supported_backends=["llama.cpp"],
            supported_quantizations=["q4_k_m"],
        ),
    )
    with pytest.raises(ValidationError, match="invalid version"):
        validate_agent(a)


def test_preferred_not_in_supported():
    a = Agent(
        name="bad",
        capabilities=AgentCapability(
            supported_models=["m1"],
            preferred_models=["m2"],
            supported_backends=["llama.cpp"],
            supported_quantizations=["q4_k_m"],
        ),
    )
    with pytest.raises(ValidationError, match="preferred_models"):
        validate_agent(a)


def test_allow_unknown_backend():
    a = Agent(
        name="ok",
        capabilities=AgentCapability(supported_backends=["custom-backend"]),
    )
    validate_agent(a, allow_unknown_backend=True, allow_unknown_quant=True)
