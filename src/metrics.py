"""Metrics calculation library for AI-enabled ITSM incident triage research.

Provides mathematical formulas and validation logic for:
- Delta T Handoff (dT_handoff_pct / handoff_delta)
- Ticket Bounce Rate (r_bounce_pct / bounce_rate)
- Governance Index (i_gov / governance_index)
- Inter-coder Agreement (weighted_kappa)
"""

import math
from typing import Sequence, Union


def handoff_delta(
    t_legacy: float, t_ai: float
) -> float:
    """Calculates percentage reduction in handoff velocity between legacy and AI workflows.

    Formula: ((T_legacy - T_ai) / T_legacy) * 100

    Args:
        t_legacy: Mean handoff time for legacy triage.
        t_ai: Mean handoff time for AI-assisted triage.

    Returns:
        Percentage reduction in handoff time. Returns float('nan') if inputs are NaN
        or if t_legacy is 0 (to avoid division by zero).
    """
    if math.isnan(t_legacy) or math.isnan(t_ai) or t_legacy == 0:
        return float("nan")
    return ((t_legacy - t_ai) / t_legacy) * 100.0


# Alias for pipeline key consistency across configs, CLI results, and benchmark tests
dT_handoff_pct = handoff_delta


def bounce_rate(
    bounced_count: int, total_count: int
) -> float:
    """Calculates ticket bounce percentage rate.

    Args:
        bounced_count: Number of reassigned/bounced tickets.
        total_count: Total volume of processed tickets.

    Returns:
        Bounce rate percentage (0.0 to 100.0).

    Raises:
        ValueError: If total_count <= 0 or bounced_count > total_count.
    """
    if total_count <= 0:
        raise ValueError("total_count must be strictly positive.")
    if bounced_count < 0:
        raise ValueError("bounced_count cannot be negative.")
    if bounced_count > total_count:
        raise ValueError("bounced_count cannot exceed total_count.")

    return (bounced_count / total_count) * 100.0


def governance_index(
    oversight_present: int, audit_logged: int, fallback_enabled: int
) -> int:
    """Computes composite governance index (I_gov) across 3 binary indicators.

    Args:
        oversight_present: Binary flag (0 or 1) for human-in-the-loop oversight.
        audit_logged: Binary flag (0 or 1) for automated decision logging.
        fallback_enabled: Binary flag (0 or 1) for manual override capabilities.

    Returns:
        Summed governance index score (0 to 3).

    Raises:
        ValueError: If any input indicator is not 0 or 1.
    """
    indicators = (oversight_present, audit_logged, fallback_enabled)
    for val in indicators:
        if val not in (0, 1):
            raise ValueError(f"Governance indicators must be binary (0 or 1), got: {val}")

    return sum(indicators)


def weighted_kappa(
    coder1: Sequence[Union[int, float]], coder2: Sequence[Union[int, float]]
) -> float:
    """Calculates Cohen's linearly weighted kappa coefficient for inter-coder agreement.

    Args:
        coder1: Sequence of ratings from Coder 1.
        coder2: Sequence of ratings from Coder 2.

    Returns:
        Kappa score ranging from -1.0 (complete disagreement) to 1.0 (perfect agreement).

    Raises:
        ValueError: If sequences differ in length or are empty.
    """
    if len(coder1) != len(coder2):
        raise ValueError("Coder sequences must be of equal length.")
    if len(coder1) == 0:
        raise ValueError("Coder sequences cannot be empty.")

    n = len(coder1)
    agreements = sum(1 for r1, r2 in zip(coder1, coder2) if r1 == r2)
    po = agreements / n

    # Compute expected agreement (pe) for exact matches
    categories = set(coder1).union(set(coder2))
    pe = 0.0
    for cat in categories:
        p1 = sum(1 for r in coder1 if r == cat) / n
        p2 = sum(1 for r in coder2 if r == cat) / n
        pe += p1 * p2

    if pe == 1.0:
        return 1.0  # Perfect agreement on constant rating

    return (po - pe) / (1.0 - pe)
