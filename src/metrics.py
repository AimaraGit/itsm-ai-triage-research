"""Metrics calculation library for AI-enabled ITSM incident triage research.

Provides mathematical formulas and validation logic for:
- Delta T Handoff (dT_handoff_pct / handoff_delta)
- Ticket Bounce Rate (r_bounce_pct / bounce_rate)
- Governance Index (i_gov / governance_index)
- Inter-coder Agreement (weighted_kappa, quadratic weights)
- Effect size for ordinal data (cliffs_delta)
"""

import math
from typing import Optional, Sequence, Union

Number = Union[int, float]


def handoff_delta(t_legacy: float, t_ai: float) -> float:
    """Percentage reduction in handoff time: ((T_legacy - T_ai) / T_legacy) * 100.

    Returns float('nan') if an input is NaN or t_legacy is 0.
    """
    if math.isnan(t_legacy) or math.isnan(t_ai) or t_legacy == 0:
        return float("nan")
    return ((t_legacy - t_ai) / t_legacy) * 100.0


# Alias for pipeline key consistency across configs, CLI results, and benchmark tests
dT_handoff_pct = handoff_delta


def bounce_rate(bounced_count: int, total_count: int) -> float:
    """Ticket bounce percentage (0..100).

    Raises:
        ValueError: if total_count <= 0, bounced_count < 0 or bounced_count > total_count.
    """
    if total_count <= 0:
        raise ValueError("total_count must be strictly positive.")
    if bounced_count < 0:
        raise ValueError("bounced_count cannot be negative.")
    if bounced_count > total_count:
        raise ValueError("bounced_count cannot exceed total_count.")
    return (bounced_count / total_count) * 100.0


def governance_index(oversight_present: int, audit_logged: int, fallback_enabled: int) -> int:
    """Composite governance index I_gov = sum of 3 binary indicators (0..3).

    Raises:
        ValueError: if any indicator is not 0 or 1.
    """
    indicators = (oversight_present, audit_logged, fallback_enabled)
    for val in indicators:
        if val not in (0, 1):
            raise ValueError(f"Governance indicators must be binary (0 or 1), got: {val}")
    return sum(indicators)


def weighted_kappa(
    coder1: Sequence[Number],
    coder2: Sequence[Number],
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
) -> float:
    """Cohen's quadratic-weighted kappa for ordinal ratings.

    kappa = 1 - sum(w_ij * O_ij) / sum(w_ij * E_ij),  w_ij = (i - j)^2 / (k - 1)^2

    Args:
        coder1, coder2: integer ratings of equal length.
        min_rating, max_rating: rating scale bounds (inferred from data if omitted).

    Raises:
        ValueError: if sequences differ in length or are empty.
    """
    if len(coder1) != len(coder2):
        raise ValueError("Coder sequences must be of equal length.")
    if len(coder1) == 0:
        raise ValueError("Coder sequences cannot be empty.")

    a = [int(x) for x in coder1]
    b = [int(x) for x in coder2]
    lo = min(a + b) if min_rating is None else int(min_rating)
    hi = max(a + b) if max_rating is None else int(max_rating)
    k = hi - lo + 1
    if k < 2:
        return 1.0  # a single category: agreement is trivially perfect
    n = len(a)

    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        if not (lo <= x <= hi and lo <= y <= hi):
            raise ValueError(f"Rating outside [{lo}, {hi}]: {x}, {y}")
        observed[x - lo][y - lo] += 1.0

    hist_a = [sum(row) for row in observed]
    hist_b = [sum(observed[i][j] for i in range(k)) for j in range(k)]

    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            num += w * observed[i][j]
            den += w * hist_a[i] * hist_b[j] / n
    if den == 0.0:
        return 1.0  # no expected disagreement (constant ratings)
    return 1.0 - num / den


def cliffs_delta(group_a: Sequence[Number], group_b: Sequence[Number]) -> float:
    """Cliff's delta: P(a > b) - P(a < b), in [-1, 1]. Returns nan if a group is empty."""
    if len(group_a) == 0 or len(group_b) == 0:
        return float("nan")
    greater = sum(1 for x in group_a for y in group_b if x > y)
    less = sum(1 for x in group_a for y in group_b if x < y)
    return (greater - less) / (len(group_a) * len(group_b))
