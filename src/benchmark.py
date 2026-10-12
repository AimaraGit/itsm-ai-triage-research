"""Measurement pipeline for the ITSM AI-triage study.

Usage:  python -m src.benchmark --config configs/config.yaml

Reads coded cases (output of the Document Analysis Protocol), computes DV1-DV4
indices, tests H1.1 / H1.2 / H1.3, evaluates guardrail metrics and writes
results/metrics.csv, results/hypothesis_tests.csv and results/run.log.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats

from src.metrics import bounce_rate, governance_index, handoff_delta, weighted_kappa

REQUIRED_COLUMNS = [
    "case_id", "group", "source_type", "triage_type", "autonomy_level", "hitl_score",
    "t_legacy_min", "t_ai_min", "n_misrouted", "n_total",
    "esc_thresholds", "circuit_breaker", "audit_logging",
]
log = logging.getLogger("benchmark")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_cases(path: str, cfg: dict) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"cases file is missing columns: {missing}")
    if df["case_id"].duplicated().any():
        raise ValueError("duplicate case_id values")
    if not df["group"].isin(cfg["groups"].keys()).all():
        raise ValueError(f"group must be one of {list(cfg['groups'])}")
    if not df["triage_type"].isin(cfg["independent_variables"]["triage_type"].keys()).all():
        raise ValueError("triage_type has values outside the configured set")
    if not df["autonomy_level"].isin(cfg["independent_variables"]["autonomy_level"].keys()).all():
        raise ValueError("autonomy_level has values outside the configured set")
    if not df["hitl_score"].between(1, 5).all():
        raise ValueError("hitl_score must be in 1..5")
    return df


def add_indices(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["dT_handoff_pct"] = [handoff_delta(a, b) for a, b in zip(df["t_legacy_min"], df["t_ai_min"])]
    df["r_bounce_pct"] = [bounce_rate(m, n) for m, n in zip(df["n_misrouted"], df["n_total"])]
    df["i_gov"] = [governance_index(int(a), int(b), int(c))
                   for a, b, c in zip(df["esc_thresholds"], df["circuit_breaker"], df["audit_logging"])]
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("group")
    out = pd.DataFrame({
        "n_cases": g.size(),
        "hitl_score_mean": g["hitl_score"].mean(),
        "dT_handoff_pct_mean": g["dT_handoff_pct"].mean(),
        "r_bounce_pct_mean": g["r_bounce_pct"].mean(),
        "i_gov_mean": g["i_gov"].mean(),
    }).round(2)
    return out.reset_index()


def _decision(p: float, n_ok: bool, alpha: float) -> str:
    if not n_ok:
        return "INSUFFICIENT_N"
    return "REJECT_H0" if p < alpha else "FAIL_TO_REJECT_H0"


def run_tests(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    alpha = cfg["statistics"]["alpha"]
    min_n = cfg["statistics"]["min_group_size"]
    rows = []

    # H1.1: hitl_score (DV1) higher for ML triage than legacy (Mann-Whitney U, one-sided)
    ml = df.loc[df.triage_type == 1, "hitl_score"]
    legacy = df.loc[df.triage_type == 0, "hitl_score"]
    ok = len(ml) >= min_n and len(legacy) >= min_n
    res = stats.mannwhitneyu(ml, legacy, alternative="greater") if ok else None
    p = float(res.pvalue) if res else float("nan")
    rows.append({"hypothesis": "H1.1", "variable": "DV1 hitl_score", "test": "Mann-Whitney U (ML > legacy)",
                 "n": f"{len(ml)}/{len(legacy)}", "statistic": float(res.statistic) if res else np.nan,
                 "p_value": p, "alpha": alpha, "decision": _decision(p, ok, alpha)})

    # H1.2 (primary): handoff time shorter with AI (Wilcoxon signed-rank on matched pairs)
    pairs = df.dropna(subset=["t_legacy_min", "t_ai_min"])
    ok = len(pairs) >= min_n
    res = stats.wilcoxon(pairs["t_legacy_min"], pairs["t_ai_min"], alternative="greater") if ok else None
    p = float(res.pvalue) if res else float("nan")
    rows.append({"hypothesis": "H1.2 (primary)", "variable": "DV2 dT_handoff_pct",
                 "test": "Wilcoxon signed-rank (T_legacy > T_AI)", "n": str(len(pairs)),
                 "statistic": float(res.statistic) if res else np.nan, "p_value": p,
                 "alpha": alpha, "decision": _decision(p, ok, alpha)})

    # H1.2 (secondary): re-routing rate lower with AI (Mann-Whitney U, one-sided)
    leg_r = df.loc[df.triage_type == 0, "r_bounce_pct"]
    ai_r = df.loc[df.triage_type == 1, "r_bounce_pct"]
    ok = len(leg_r) >= min_n and len(ai_r) >= min_n
    res = stats.mannwhitneyu(leg_r, ai_r, alternative="greater") if ok else None
    p = float(res.pvalue) if res else float("nan")
    rows.append({"hypothesis": "H1.2 (secondary)", "variable": "DV3 r_bounce_pct",
                 "test": "Mann-Whitney U (legacy > AI)", "n": f"{len(leg_r)}/{len(ai_r)}",
                 "statistic": float(res.statistic) if res else np.nan, "p_value": p,
                 "alpha": alpha, "decision": _decision(p, ok, alpha)})

    # H1.3: governance index rises with autonomy level (Spearman, one-sided)
    ok = len(df) >= min_n and df["autonomy_level"].nunique() > 1 and df["i_gov"].nunique() > 1
    res = stats.spearmanr(df["autonomy_level"], df["i_gov"], alternative="greater") if ok else None
    p = float(res.pvalue) if res else float("nan")
    rows.append({"hypothesis": "H1.3", "variable": "IV2 autonomy_level vs DV4 i_gov",
                 "test": "Spearman rho (positive)", "n": str(len(df)),
                 "statistic": float(res.statistic) if res else np.nan, "p_value": p,
                 "alpha": alpha, "decision": _decision(p, ok, alpha)})
    out = pd.DataFrame(rows)
    out[["statistic", "p_value"]] = out[["statistic", "p_value"]].round(4)
    return out


def check_guardrails(df: pd.DataFrame, cfg: dict, coder_csv: str | None) -> pd.DataFrame:
    gr = cfg["guardrails"]
    rows = []

    ai_bounce = float(df.loc[df.triage_type == 1, "r_bounce_pct"].mean())
    rows.append(("G1_ai_bounce_rate_pct", round(ai_bounce, 2), f"<= {gr['max_ai_bounce_rate_pct']}",
                 ai_bounce <= gr["max_ai_bounce_rate_pct"]))

    if coder_csv and Path(coder_csv).exists():
        cc = pd.read_csv(coder_csv)
        kappa = weighted_kappa(cc["coder_a"], cc["coder_b"])
        rows.append(("G2_weighted_kappa_dv1", round(kappa, 3), f">= {gr['min_weighted_kappa']}",
                     bool(kappa >= gr["min_weighted_kappa"])))
    else:
        rows.append(("G2_weighted_kappa_dv1", np.nan, f">= {gr['min_weighted_kappa']}", False))

    share = float(df["source_type"].isin(gr["third_party_sources"]).mean())
    rows.append(("G3_third_party_share", round(share, 2), f">= {gr['min_third_party_share']}",
                 share >= gr["min_third_party_share"]))

    if gr.get("forbid_full_autonomy_without_governance", False):
        bad = int(((df.autonomy_level == 3) & (df.i_gov == 0)).sum())
        rows.append(("G4_full_autonomy_without_governance", bad, "== 0", bad == 0))

    out = pd.DataFrame(rows, columns=["guardrail", "value", "threshold", "passed"])
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ITSM AI-triage measurement pipeline")
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    cfg = load_config(args.config)
    out_dir = Path(cfg["paths"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(out_dir / "run.log", mode="w", encoding="utf-8")])
    np.random.seed(cfg["experiment"]["random_seed"])

    if cfg["experiment"].get("is_sample", False):
        log.warning("SAMPLE DATA - pipeline check only, results are NOT evidence.")

    df = add_indices(load_cases(cfg["paths"]["cases_csv"], cfg))
    log.info("Loaded %d coded cases", len(df))

    summary = summarize(df)
    tests = run_tests(df, cfg)
    guards = check_guardrails(df, cfg, cfg["paths"].get("coder_agreement_csv"))

    summary.to_csv(out_dir / "metrics.csv", index=False)
    tests.to_csv(out_dir / "hypothesis_tests.csv", index=False)
    guards.to_csv(out_dir / "guardrails.csv", index=False)

    log.info("Group summary:\n%s", summary.to_string(index=False))
    log.info("Hypothesis tests:\n%s", tests.to_string(index=False))
    log.info("Guardrails:\n%s", guards.to_string(index=False))

    elapsed = time.perf_counter() - t0
    log.info("Done in %.2f s -> %s", elapsed, out_dir.resolve())
    if elapsed > cfg["experiment"]["timeout_sec"]:
        log.warning("Run exceeded timeout_sec=%s", cfg["experiment"]["timeout_sec"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
