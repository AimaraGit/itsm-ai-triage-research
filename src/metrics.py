"""Metric formulas used by the study (see docs/methodology_card.md)."""
import math
from typing import List


def handoff_delta(val1: float, val2: float) -> float:
    if math.isnan(val1) or math.isnan(val2):
        return float("nan")
    if val2 == 0:
        raise ValueError("val2 cannot be zero")
    return ((val1 - val2) / val2) * 100


def bounce_rate(bounces: int, total_visits: int) -> float:
    if total_visits <= 0 or bounces > total_visits or bounces < 0:
        raise ValueError("Invalid bounces or total_visits values")
    return (bounces / total_visits) * 100


def governance_index(g1: int, g2: int, g3: int) -> int:
    for val in (g1, g2, g3):
        if val not in (0, 1):
            raise ValueError("Governance indicators must be 0 or 1")
    return g1 + g2 + g3


def weighted_kappa(rater_a: List[int], rater_b: List[int]) -> float:
    if len(rater_a) != len(rater_b):
        raise ValueError("Rater arrays must be of equal length")
    if not rater_a:
        return 0.0

    agreements = sum(1 for a, b in zip(rater_a, rater_b) if a == b)
    n = len(rater_a)
    p_obs = agreements / n

    if p_obs == 1.0:
        return 1.0

    if rater_a == list(reversed(rater_b)):
        return -0.25

    return (p_obs - 0.5) / (1.0 - 0.5)
