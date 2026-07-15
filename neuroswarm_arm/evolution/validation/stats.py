"""Statistical validation helpers."""

from __future__ import annotations

import math
import random
from typing import Sequence


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def variance(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def welch_t_test(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Return (t_statistic, approximate two-sided p-value via normal approx)."""
    if len(a) < 2 or len(b) < 2:
        return 0.0, 1.0
    ma, mb = mean(a), mean(b)
    va, vb = variance(a), variance(b)
    na, nb = len(a), len(b)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return 0.0, 1.0
    t = (ma - mb) / se
    # Normal approximation for p-value
    p = 2.0 * (1.0 - _norm_cdf(abs(t)))
    return t, max(0.0, min(1.0, p))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bootstrap_mean_ci(
    samples: Sequence[float],
    *,
    n_boot: int = 200,
    alpha: float = 0.1,
    rng: random.Random | None = None,
) -> tuple[float, float, float]:
    """Return (mean, lo, hi) percentile CI."""
    if not samples:
        return 0.0, 0.0, 0.0
    r = rng or random.Random(0)
    boots: list[float] = []
    n = len(samples)
    for _ in range(n_boot):
        draw = [samples[r.randrange(n)] for _ in range(n)]
        boots.append(mean(draw))
    boots.sort()
    lo_i = int(alpha / 2 * n_boot)
    hi_i = min(n_boot - 1, int((1 - alpha / 2) * n_boot))
    return mean(samples), boots[lo_i], boots[hi_i]


def effect_size(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d (candidate - baseline)."""
    if not a or not b:
        return 0.0
    ma, mb = mean(a), mean(b)
    pooled = math.sqrt((variance(a) + variance(b)) / 2.0) or 1.0
    return (ma - mb) / pooled
