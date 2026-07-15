"""Eviction policies."""

from ..models import EvictionPolicyName
from ..interfaces import IEvictionPolicy
from .arc import ARCPolicy
from .cost_aware import CostAwarePolicy
from .lfu import LFUPolicy
from .lru import LRUPolicy
from .scored import EvictionWeights, ScoredEvictionPolicy
from .temperature import TemperaturePolicy


def build_policy(name: EvictionPolicyName | str) -> IEvictionPolicy:
    key = EvictionPolicyName(name) if isinstance(name, str) else name
    if key is EvictionPolicyName.SCORED:
        return ScoredEvictionPolicy()
    if key is EvictionPolicyName.LFU:
        return LFUPolicy()
    if key is EvictionPolicyName.ARC:
        return ARCPolicy()
    if key is EvictionPolicyName.TEMPERATURE:
        return TemperaturePolicy()
    if key is EvictionPolicyName.COST_AWARE:
        return CostAwarePolicy()
    # CLOCK uses LRU-like ordering with clock hand in EvictionEngine
    return LRUPolicy()


__all__ = [
    "LRUPolicy",
    "LFUPolicy",
    "ARCPolicy",
    "TemperaturePolicy",
    "CostAwarePolicy",
    "ScoredEvictionPolicy",
    "EvictionWeights",
    "build_policy",
]
