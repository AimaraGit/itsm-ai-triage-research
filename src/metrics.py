"""Metric formulas used by the study (see docs/methodology_card.md)."""
import math
from typing import List, Optional, Sequence
 
 
def handoff_delta(val1: float, val2: float) -> float:
    """DV2: (T_legacy - T_AI) / T_legacy * 100. NaN if either value is missing."""
    if math.isnan(val1) or math.isnan(val2):
        return float("nan")
    if val1 == 0:
        raise ValueError("val1 cannot be zero")
    return ((val1 - val2) / val1) * 100
 
 
def bounce_rate(bounces: int, total_visits: int) -> float:
    """DV3: R_bounce = N_misrouted / N_total * 100."""
    if total_visits <= 0 or bounces > total_visits or bounces < 0:
        raise ValueError("Invalid bounces or total_visits values")
    return (bounces / total_visits) * 100
 
 
def governance_index(g1: int, g2: int, g3: int) -> int:
    """DV4: I_gov = escalation thresholds + circuit breaker + audit logging (0-3)."""
    for val in (g1, g2, g3):
        if val not in (0, 1):
            raise ValueError("Governance indicators must be 0 or 1")
    return g1 + g2 + g3
 
 
def weighted_kappa(
    rater_a: Sequence[int],
    rater_b: Sequence[int],
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
) -> float:
    """Quadratic-weighted Cohen's kappa (guardrail G2).
 
    kappa = 1 - sum(w * observed) / sum(w * expected), with
    w_ij = (i - j)^2 / (k - 1)^2 and expected counts from the raters' marginals.
    Ratings are integers; the scale is min_rating..max_rating (inferred from
    the data when not given, pass 1 and 5 for the DV1 scale).
    """
    if len(rater_a) != len(rater_b):
        raise ValueError("Rater arrays must be of equal length")
    if not len(rater_a):
        return 0.0
 
    lo = min(min(rater_a), min(rater_b)) if min_rating is None else min_rating
    hi = max(max(rater_a), max(rater_b)) if max_rating is None else max_rating
    k = hi - lo + 1
    if k < 2:
        return 1.0
 
    observed = [[0.0] * k for _ in range(k)]
    for a, b in zip(rater_a, rater_b):
        if not (lo <= a <= hi and lo <= b <= hi):
            raise ValueError(f"Rating outside the scale {lo}..{hi}: ({a}, {b})")
        observed[a - lo][b - lo] += 1
 
    n = float(len(rater_a))
    hist_a = [sum(row) for row in observed]
    hist_b = [sum(observed[i][j] for i in range(k)) for j in range(k)]
 
    num = 0.0
    den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            num += w * observed[i][j]
            den += w * hist_a[i] * hist_b[j] / n
 
    if den == 0:  # both raters used one identical category only
        return 1.0
    return 1.0 - num / den
 
 
def cliffs_delta(x: Sequence[float], y: Sequence[float]) -> float:
    """Effect size for Mann-Whitney U: P(x > y) - P(x < y), range -1..1."""
    if not len(x) or not len(y):
        return float("nan")
    greater = sum(1 for a in x for b in y if a > b)
    less = sum(1 for a in x for b in y if a < b)
    return (greater - less) / (len(x) * len(y))
