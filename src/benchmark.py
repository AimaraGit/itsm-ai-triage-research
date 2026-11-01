"""Measurement pipeline for the ITSM AI-triage study.
 
Usage:  python -m src.benchmark --config configs/config.yaml [--strict]
 
Reads coded cases (output of the Document Analysis Protocol), computes DV1-DV4,
tests H1.1 / H1.2 / H1.3, evaluates guardrails G1-G4 and writes into
paths.output_dir:
    metrics.csv, hypothesis_tests.csv, guardrails.csv, run.log,
    benchmark_runs.jsonl, benchmark_summary.json
"""
import argparse
import json
import platform
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
 
import numpy as np
import pandas as pd
import psutil
import yaml
from scipy import stats
 
from src.metrics import (
    bounce_rate,
    cliffs_delta,
    governance_index,
    handoff_delta,
    weighted_kappa,
)
 
REQUIRED_COLUMNS = [
    "case_id", "group", "source_type", "triage_type", "autonomy_level",
    "hitl_score", "t_legacy_min", "t_ai_min", "n_misrouted", "n_total",
    "esc_thresholds", "circuit_breaker", "audit_logging",
]
 
 
# --------------------------------------------------------------------------
# Environment and timing
# --------------------------------------------------------------------------
def get_system_metadata() -> Dict[str, Any]:
    """Records the environment parameters of the run."""
    return {
        "python_version": sys.version.split()[0],
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
    }
 
 
def execute_isolated_benchmark(
    target_fn: Callable[..., Any],
    fn_args: Tuple[Any, ...],
    fn_kwargs: Dict[str, Any],
    warmup_runs: int = 15,
    test_runs: int = 100,
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Warm-up phase, then an isolated timing loop (no file I/O inside the loop)."""
    for _ in range(warmup_runs):
        try:
            target_fn(*fn_args, **fn_kwargs)
        except Exception:
            pass
 
    records: List[Dict[str, Any]] = []
    latencies_ns: List[float] = []
 
    for i in range(test_runs):
        status = "success"
        error_msg: Optional[str] = None
 
        t0 = time.perf_counter_ns()
        try:
            _ = target_fn(*fn_args, **fn_kwargs)
        except Exception as e:
            status = "error"
            error_msg = str(e)
        t1 = time.perf_counter_ns()
 
        if status == "success":
            latencies_ns.append(t1 - t0)
 
        records.append({
            "iteration": i,
            "latency_ms": (t1 - t0) / 1e6,
            "status": status,
            "error": error_msg,
            "timestamp_ns": t1,
        })
 
    if not latencies_ns:
        aggregated_metrics = {"error_rate_pct": 100.0}
    else:
        latencies_ms = np.array(latencies_ns) / 1e6
        aggregated_metrics = {
            "p50_ms": float(np.percentile(latencies_ms, 50)),
            "p95_ms": float(np.percentile(latencies_ms, 95)),
            "p99_ms": float(np.percentile(latencies_ms, 99)),
            "mean_ms": float(np.mean(latencies_ms)),
            "std_ms": float(np.std(latencies_ms)),
            "error_rate_pct": float(((test_runs - len(latencies_ms)) / test_runs) * 100),
        }
    return records, aggregated_metrics
 
 
# --------------------------------------------------------------------------
# Data loading and derived variables
# --------------------------------------------------------------------------
def load_cases(path: Path) -> pd.DataFrame:
    """Reads cases.csv and validates it against the codebook (docs/codebook.md)."""
    if not Path(path).exists():
        raise FileNotFoundError(f"Cases file not found: {path}")
    df = pd.read_csv(path)
 
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"cases.csv is missing columns: {missing}")
    if df["case_id"].duplicated().any():
        raise ValueError("case_id must be unique")
 
    checks = {
        "triage_type": {0, 1},
        "autonomy_level": {1, 2, 3},
        "hitl_score": {1, 2, 3, 4, 5},
        "esc_thresholds": {0, 1},
        "circuit_breaker": {0, 1},
        "audit_logging": {0, 1},
    }
    for col, allowed in checks.items():
        bad = set(df[col].dropna().unique()) - allowed
        if bad or df[col].isna().any():
            raise ValueError(f"Column {col}: values must be in {sorted(allowed)}, got {sorted(bad)} / NaN")
    return df
 
 
def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Adds dT_handoff_pct (DV2), r_bounce_pct (DV3) and i_gov (DV4)."""
    out = df.copy()
    out["dT_handoff_pct"] = [
        handoff_delta(a, b) for a, b in zip(out["t_legacy_min"], out["t_ai_min"])
    ]
    out["r_bounce_pct"] = [
        bounce_rate(int(m), int(t)) for m, t in zip(out["n_misrouted"], out["n_total"])
    ]
    out["i_gov"] = [
        governance_index(int(a), int(b), int(c))
        for a, b, c in zip(out["esc_thresholds"], out["circuit_breaker"], out["audit_logging"])
    ]
    return out
 
 
# --------------------------------------------------------------------------
# Hypothesis tests
# --------------------------------------------------------------------------
def _row(hyp: str, test: str, alt: str, n1: int, n2: Optional[int], stat: float,
         p: float, eff_name: str, eff: float, alpha: float, note: str = "") -> Dict[str, Any]:
    if np.isnan(p):
        decision = "not_tested"
    else:
        decision = "reject_H0" if p < alpha else "fail_to_reject_H0"
    return {
        "hypothesis": hyp, "test": test, "alternative": alt,
        "n_1": n1, "n_2": n2, "statistic": stat, "p_value": p,
        "effect_size_name": eff_name, "effect_size": eff,
        "alpha": alpha, "decision": decision, "note": note,
    }
 
 
def _skipped(hyp: str, test: str, alt: str, n1: int, n2: Optional[int],
             alpha: float, reason: str) -> Dict[str, Any]:
    return _row(hyp, test, alt, n1, n2, float("nan"), float("nan"),
                "", float("nan"), alpha, note=reason)
 
 
def run_hypothesis_tests(df: pd.DataFrame, alpha: float, min_n: int) -> List[Dict[str, Any]]:
    """H1.1 Mann-Whitney U, H1.2 Wilcoxon (+ R_bounce Mann-Whitney), H1.3 Spearman.
 
    All tests are one-sided with the direction fixed in advance.
    """
    rows: List[Dict[str, Any]] = []
    ai = df[df["triage_type"] == 1]
    legacy = df[df["triage_type"] == 0]
 
    # H1.1: HITL embedding score, ML-triage > legacy
    name, alt = "H1.1 DV1 hitl_score: AI > legacy", "greater"
    if len(ai) < min_n or len(legacy) < min_n:
        rows.append(_skipped(name, "Mann-Whitney U", alt, len(ai), len(legacy), alpha,
                             f"insufficient_n (min {min_n} per group)"))
    else:
        res = stats.mannwhitneyu(ai["hitl_score"], legacy["hitl_score"], alternative=alt)
        rows.append(_row(name, "Mann-Whitney U", alt, len(ai), len(legacy),
                         float(res.statistic), float(res.pvalue), "cliffs_delta",
                         cliffs_delta(list(ai["hitl_score"]), list(legacy["hitl_score"])), alpha))
 
    # H1.2 (primary): paired handoff times, T_legacy - T_AI > 0
    name, alt = "H1.2 DV2 handoff time: T_legacy - T_AI > 0", "greater"
    paired = ai.dropna(subset=["t_legacy_min", "t_ai_min"])
    if len(paired) < min_n:
        rows.append(_skipped(name, "Wilcoxon signed-rank", alt, len(paired), None, alpha,
                             f"insufficient_n (min {min_n} pairs)"))
    else:
        diff = paired["t_legacy_min"] - paired["t_ai_min"]
        if (diff == 0).all():
            rows.append(_skipped(name, "Wilcoxon signed-rank", alt, len(paired), None, alpha,
                                 "all paired differences are zero"))
        else:
            res = stats.wilcoxon(diff, alternative=alt)
            rows.append(_row(name, "Wilcoxon signed-rank", alt, len(paired), None,
                             float(res.statistic), float(res.pvalue), "median_diff_min",
                             float(diff.median()), alpha,
                             note=f"median dT_handoff = {paired['dT_handoff_pct'].median():.1f} %"))
 
    # H1.2 (secondary): re-routing rate, AI < legacy
    name, alt = "H1.2 DV3 r_bounce: AI < legacy", "less"
    if len(ai) < min_n or len(legacy) < min_n:
        rows.append(_skipped(name, "Mann-Whitney U", alt, len(ai), len(legacy), alpha,
                             f"insufficient_n (min {min_n} per group)"))
    else:
        res = stats.mannwhitneyu(ai["r_bounce_pct"], legacy["r_bounce_pct"], alternative=alt)
        rows.append(_row(name, "Mann-Whitney U", alt, len(ai), len(legacy),
                         float(res.statistic), float(res.pvalue), "cliffs_delta",
                         cliffs_delta(list(ai["r_bounce_pct"]), list(legacy["r_bounce_pct"])), alpha))
 
    # H1.3: autonomy (IV2) vs governance index (DV4), rho > 0
    name, alt = "H1.3 IV2 autonomy vs DV4 i_gov: rho > 0", "greater"
    if len(df) < min_n:
        rows.append(_skipped(name, "Spearman rho", alt, len(df), None, alpha,
                             f"insufficient_n (min {min_n})"))
    elif df["autonomy_level"].nunique() < 2 or df["i_gov"].nunique() < 2:
        rows.append(_skipped(name, "Spearman rho", alt, len(df), None, alpha,
                             "no variation in autonomy_level or i_gov"))
    else:
        res = stats.spearmanr(df["autonomy_level"], df["i_gov"], alternative=alt)
        rows.append(_row(name, "Spearman rho", alt, len(df), None,
                         float(res.statistic), float(res.pvalue), "rho",
                         float(res.statistic), alpha))
    return rows
 
 
# --------------------------------------------------------------------------
# Guardrails G1-G4
# --------------------------------------------------------------------------
def evaluate_guardrails(df: pd.DataFrame, agreement: Optional[pd.DataFrame],
                        g_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pre-registered guardrails; thresholds come from config.yaml."""
    rows: List[Dict[str, Any]] = []
 
    # G1: mean re-routing rate of AI cases <= threshold
    ai = df[df["triage_type"] == 1]
    val = float(ai["r_bounce_pct"].mean()) if len(ai) else float("nan")
    thr = float(g_cfg["max_ai_bounce_rate_pct"])
    rows.append({"id": "G1", "guardrail": "mean R_bounce of AI cases (%)", "value": val,
                 "threshold": thr, "rule": "<=", "passed": bool(len(ai) and val <= thr)})
 
    # G2: inter-coder agreement on DV1 (quadratic-weighted kappa) >= threshold
    thr = float(g_cfg["min_weighted_kappa"])
    if agreement is None or agreement.empty:
        rows.append({"id": "G2", "guardrail": "weighted kappa on DV1", "value": float("nan"),
                     "threshold": thr, "rule": ">=", "passed": False})
    else:
        kappa = weighted_kappa(list(agreement["coder_a"]), list(agreement["coder_b"]),
                               min_rating=1, max_rating=5)
        rows.append({"id": "G2", "guardrail": "weighted kappa on DV1", "value": kappa,
                     "threshold": thr, "rule": ">=", "passed": bool(kappa >= thr)})
 
    # G3: share of evidence from independent sources >= threshold
    thr = float(g_cfg["min_third_party_share"])
    share = float(df["source_type"].isin(g_cfg["third_party_sources"]).mean())
    rows.append({"id": "G3", "guardrail": "share of independent sources", "value": share,
                 "threshold": thr, "rule": ">=", "passed": bool(share >= thr)})
 
    # G4: no case with full autonomy and no governance protocol
    if g_cfg.get("forbid_full_autonomy_without_governance", True):
        bad = int(((df["autonomy_level"] == 3) & (df["i_gov"] == 0)).sum())
        rows.append({"id": "G4", "guardrail": "cases with autonomy=3 and I_gov=0", "value": float(bad),
                     "threshold": 0.0, "rule": "==", "passed": bad == 0})
    return rows
 
 
# --------------------------------------------------------------------------
# Descriptive metrics
# --------------------------------------------------------------------------
def descriptive_metrics(df: pd.DataFrame) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for grp, sub in df.groupby("group", sort=True):
        rows.append({"scope": grp, "metric": "n_cases", "value": float(len(sub))})
        rows.append({"scope": grp, "metric": "hitl_score_median", "value": float(sub["hitl_score"].median())})
        rows.append({"scope": grp, "metric": "r_bounce_pct_mean", "value": float(sub["r_bounce_pct"].mean())})
        rows.append({"scope": grp, "metric": "i_gov_mean", "value": float(sub["i_gov"].mean())})
        dt = sub["dT_handoff_pct"].dropna()
        rows.append({"scope": grp, "metric": "dT_handoff_pct_mean",
                     "value": float(dt.mean()) if len(dt) else float("nan")})
        rows.append({"scope": grp, "metric": "n_paired_handoff", "value": float(len(dt))})
    return rows
 
 
# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
def analyze(cfg: Dict[str, Any], cases: pd.DataFrame,
            agreement: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """Pure computation (no file I/O): derived variables, tests, guardrails."""
    df = add_derived(cases)
    stat_cfg = cfg["statistics"]
    return {
        "cases": df,
        "metrics": descriptive_metrics(df),
        "tests": run_hypothesis_tests(df, float(stat_cfg["alpha"]), int(stat_cfg["min_group_size"])),
        "guardrails": evaluate_guardrails(df, agreement, cfg["guardrails"]),
    }
 
 
def _round(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows).round(6)
 
 
def run_pipeline(config_path: Path) -> Dict[str, Any]:
    """Loads data, analyses it, writes the result files. Returns the analysis."""
    t_start = time.perf_counter()
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    seed = int(cfg["experiment"]["random_seed"])
    random.seed(seed)
    np.random.seed(seed)
 
    output_dir = Path(cfg["paths"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
 
    cases = load_cases(Path(cfg["paths"]["cases_csv"]))
    agr_path = Path(cfg["paths"]["coder_agreement_csv"])
    agreement = pd.read_csv(agr_path) if agr_path.exists() else None
 
    result = analyze(cfg, cases, agreement)
    _round(result["metrics"]).to_csv(output_dir / "metrics.csv", index=False)
    _round(result["tests"]).to_csv(output_dir / "hypothesis_tests.csv", index=False)
    _round(result["guardrails"]).to_csv(output_dir / "guardrails.csv", index=False)
 
    # run.log
    is_sample = bool(cfg["experiment"].get("is_sample", False))
    lines = []
    if is_sample:
        lines.append("*** SAMPLE DATA, pipeline check only. Results are NOT research findings. ***")
    lines.append(f"experiment={cfg['experiment']['name']} seed={seed} cases={len(cases)}")
    lines.append(f"environment={json.dumps(get_system_metadata())}")
    for g in result["guardrails"]:
        lines.append(f"{g['id']} {'PASS' if g['passed'] else 'FAIL'}: {g['guardrail']} "
                     f"= {g['value']:.4g} (required {g['rule']} {g['threshold']})")
    failed = [g["id"] for g in result["guardrails"] if not g["passed"]]
    if failed:
        lines.append(f"WARNING: guardrails failed {failed}; do not interpret hypothesis tests.")
    for t in result["tests"]:
        lines.append(f"{t['hypothesis']} | {t['test']} ({t['alternative']}) n={t['n_1']}/{t['n_2']} "
                     f"p={t['p_value']:.4g} -> {t['decision']} {t['note']}")
    elapsed = time.perf_counter() - t_start
    timeout = float(cfg["experiment"].get("timeout_sec", 60))
    if elapsed > timeout:
        lines.append(f"WARNING: pipeline took {elapsed:.1f}s (> {timeout}s)")
    lines.append(f"finished in {elapsed:.2f}s")
    (output_dir / "run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
 
    result["failed_guardrails"] = failed
    result["cfg"] = cfg
    result["log"] = lines
    return result
 
 
def main(args: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ITSM AI-triage measurement pipeline")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    parser.add_argument("--strict", action="store_true",
                        help="exit with code 2 if any guardrail fails")
    parser.add_argument("--no-timing", action="store_true",
                        help="skip the latency benchmark of the analysis step")
    parsed = parser.parse_args(args)
 
    config_path = Path(parsed.config)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
 
    result = run_pipeline(config_path)
    print("\n".join(result["log"]))
    cfg = result["cfg"]
    output_dir = Path(cfg["paths"]["output_dir"])
 
    if not parsed.no_timing:
        bench_cfg = cfg.get("benchmark", {})
        agr_path = Path(cfg["paths"]["coder_agreement_csv"])
        agreement = pd.read_csv(agr_path) if agr_path.exists() else None
        cases = load_cases(Path(cfg["paths"]["cases_csv"]))
        records, agg = execute_isolated_benchmark(
            target_fn=analyze,
            fn_args=(cfg, cases, agreement),
            fn_kwargs={},
            warmup_runs=int(bench_cfg.get("warmup_runs", 15)),
            test_runs=int(bench_cfg.get("test_runs", 100)),
        )
        metadata = get_system_metadata()
        with open(output_dir / "benchmark_runs.jsonl", "w", encoding="utf-8") as f:
            for rec in records:
                rec["metadata"] = metadata
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        (output_dir / "benchmark_summary.json").write_text(json.dumps(agg, indent=2), encoding="utf-8")
 
    if parsed.strict and result["failed_guardrails"]:
        return 2
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())
 
