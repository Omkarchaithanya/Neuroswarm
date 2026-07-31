"""NgramCache O(1) lookup microbench + correctness."""

from __future__ import annotations

import random
import time

from neuroswarm_arm.runtime.armcascade.proposal.ngram_cache import NgramCache


def _random_tokens(n: int, vocab: int = 500, seed: int = 42) -> list[str]:
    rng = random.Random(seed)
    return [f"t{rng.randint(0, vocab - 1)}" for _ in range(n)]


def test_lookup_o1_under_100us_after_add():
    tokens = _random_tokens(10_000)
    text = " ".join(tokens)
    cache = NgramCache(n=3, max_entries=1_000_000)
    cache.add(text)

    # Known n-gram from middle of sequence
    idx = 5000
    seed = tokens[idx : idx + 2]
    expected_next = tokens[idx + 2]

    # Warm once
    assert cache.lookup(seed) is not None

    t0 = time.perf_counter()
    for _ in range(100):
        hit = cache.lookup(seed)
    elapsed = time.perf_counter() - t0
    per_lookup_us = (elapsed / 100) * 1_000_000
    assert per_lookup_us < 100.0, f"lookup {per_lookup_us:.2f} µs >= 100 µs"
    assert hit is not None
    assert expected_next in hit


def test_lookup_none_for_unseen():
    cache = NgramCache(n=3)
    cache.add("alpha beta gamma delta")
    assert cache.lookup(["zzz", "yyy"]) is None
    assert cache.lookup(["alpha"]) is None  # wrong seed length
    assert cache.lookup(["alpha", "beta"]) == ["gamma"]


def test_sizeof_positive():
    cache = NgramCache(n=3)
    cache.add("a b c d e f")
    assert cache.__sizeof__() > 0
    assert len(cache) > 0
