"""Plugin registries for proposers and verifiers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from neuroswarm_arm.runtime.armcascade.interfaces.proposal import (
    ProposalStrategy,
    VerifierStrategy,
)

P = TypeVar("P", bound=ProposalStrategy)
V = TypeVar("V", bound=VerifierStrategy)

_PROPOSERS: dict[str, type[ProposalStrategy]] = {}
_VERIFIERS: dict[str, type[VerifierStrategy]] = {}


def register_proposer(name: str) -> Callable[[type[P]], type[P]]:
    def deco(cls: type[P]) -> type[P]:
        cls.name = name
        _PROPOSERS[name] = cls
        return cls

    return deco


def register_verifier(name: str) -> Callable[[type[V]], type[V]]:
    def deco(cls: type[V]) -> type[V]:
        cls.name = name
        _VERIFIERS[name] = cls
        return cls

    return deco


class ProposalRegistry:
    def __init__(self) -> None:
        self._instances: dict[str, ProposalStrategy] = {}

    def register_instance(self, strategy: ProposalStrategy) -> None:
        self._instances[strategy.name] = strategy

    def get(self, name: str) -> ProposalStrategy:
        if name in self._instances:
            return self._instances[name]
        if name not in _PROPOSERS:
            raise KeyError(f"unknown proposal strategy: {name}")
        inst = _PROPOSERS[name]()
        self._instances[name] = inst
        return inst

    def available(self) -> list[str]:
        return sorted(set(_PROPOSERS) | set(self._instances))


class VerifierRegistry:
    def __init__(self) -> None:
        self._instances: dict[str, VerifierStrategy] = {}

    def register_instance(self, strategy: VerifierStrategy) -> None:
        self._instances[strategy.name] = strategy

    def get(self, name: str) -> VerifierStrategy:
        if name in self._instances:
            return self._instances[name]
        if name not in _VERIFIERS:
            raise KeyError(f"unknown verifier strategy: {name}")
        inst = _VERIFIERS[name]()
        self._instances[name] = inst
        return inst

    def available(self) -> list[str]:
        return sorted(set(_VERIFIERS) | set(self._instances))


def known_proposers() -> list[str]:
    return sorted(_PROPOSERS)


def known_verifiers() -> list[str]:
    return sorted(_VERIFIERS)
