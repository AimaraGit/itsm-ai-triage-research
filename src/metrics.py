"""Metric formulas used by the study (see docs/methodology_card.md)."""
from __future__ import annotations

import numpy as np


def handoff_delta(t_legacy: float, t_ai: float) -> float:
    """DV2: delta T_handoff = (T_legacy - T_AI) / T_legacy * 100 (percent)."""
    if t_legacy is None or t_ai is None or np.isnan(t_legacy) or np.isnan(t_ai):
        return float("nan")
    if t_legacy <= 0:
        raise ValueError("t_legacy must be > 0")
    return (t_legacy - t_ai) / t_legacy * 100.0


def bounce_rate(n_misrouted: float, n_total: float) -> float:
    """DV3: R_bounce = N_misrouted / N_total * 100 (percent)."""
    if n_total <= 0:
        raise ValueError("n_total must be > 0")
    if n_misrouted < 0 or n_misrouted > n_total:
        raise ValueError("require 0 <= n_misrouted <= n_total")
    return n_misrouted / n_total * 100.0


def governance_index(esc_thresholds: int, circuit_breaker: int, audit_logging: int) -> int:
    """DV4: I_gov = sum of three indicators (0..3)."""
    flags = (esc_thresholds, circuit_breaker, audit_logging)
    if any(f not in (0, 1) for f in flags):
        raise ValueError("governance flags must be 0 or 1")
    return int(sum(flags))


def weighted_kappa(a, b, categories=(1, 2, 3, 4, 5)) -> float:
    """Quadratic-weighted Cohen's kappa for two coders on an ordinal scale."""
    a, b = list(a), list(b)
    if len(a) != len(b) or not a:
        raise ValueError("coder vectors must be non-empty and of equal length")
    k = len(categories)
    idx = {c: i for i, c in enumerate(categories)}
    obs = np.zeros((k, k))
    for x, y in zip(a, b):
        obs[idx[x], idx[y]] += 1
    obs /= obs.sum()
    exp = np.outer(obs.sum(axis=1), obs.sum(axis=0))
    w = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)], dtype=float) / (k - 1) ** 2
    denom = (w * exp).sum()
    if denom == 0:
        return 1.0 if (w * obs).sum() == 0 else float("nan")
    return float(1.0 - (w * obs).sum() / denom)
