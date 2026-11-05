"""Measurement pipeline for the ITSM AI-triage study.
 
Usage:  python -m src.benchmark --config configs/config.yaml [--strict]
 
Reads coded cases (output of the Document Analysis Protocol), computes DV1-DV4,
tests H1.1 / H1.2 / H1.3, evaluates guardrails G1-G4 and writes into
paths.output_dir:
    metrics.csv, hypothesis_tests.csv, guardrails.csv, run.log,
    benchmark_summary.json, and (path from benchmark.output_jsonl)
    data/raw/test_run.jsonl
"""
import argparse
import gc
import hashlib
import importlib.metadata
import json
import platform
import random
import subprocess
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
def _cpu_model() -> str:
    """CPU model name (platform.processor() returns only the arch on Linux)."""
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _cgroup_limits() -> Dict[str, Any]:
    """Docker/cgroup CPU and memory limits (None if unlimited or unavailable)."""
    out: Dict[str, Any] = {"cgroup_cpu_limit": None, "cgroup_memory_limit_bytes": None}
    try:  # cgroup v2
        cpu = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if cpu[0] != "max":
            out["cgroup_cpu_limit"] = round(int(cpu[0]) / int(cpu[1]), 2)
        mem = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if mem != "max":
            out["cgroup_memory_limit_bytes"] = int(mem)
    except (OSError, ValueError, IndexError):
        pass
    return out


def _git_commit() -> Optional[str]:
    try:
        res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=5)
        return res.stdout.strip() or None if res.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def get_system_metadata(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Records the environment parameters of the run (written ONCE per JSONL file)."""
    meta: Dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "os": platform.platform(),
        "cpu": _cpu_model(),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "git_commit": _git_commit(),
        "in_docker": Path("/.dockerenv").exists(),
        "packages": {p: importlib.metadata.version(p)
                     for p in ("numpy", "pandas", "scipy", "PyYAML", "psutil")},
    }
    meta.update(_cgroup_limits())
    if cfg is not None:
        meta["seed"] = int(cfg["experiment"]["random_seed"])
        meta["config_sha256"] = hashlib.sha256(
            json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return meta


# --------------------------------------------------------------------------
# Synthetic workload (heavy-tailed sizes + edge cases)
# --------------------------------------------------------------------------
def build_workload(cases: pd.DataFrame, n_inputs: int, wl_cfg: Dict[str, Any],
                   seed: int) -> List[Dict[str, Any]]:
    """Deterministic list of inputs for analyze().

    Input size (rows) follows a Pareto distribution (many small inputs, a few huge
    ones) instead of random.randint(); rows are resampled from the real cases with
    unique ids. A fixed share of runs uses edge cases: empty frame, single row,
    all-NaN handoff times, extreme strings in text columns, and invalid rows that
    must raise (n_total = 0), which exercises the error path on purpose.
    """
    rng = np.random.default_rng(seed)
    alpha = float(wl_cfg.get("pareto_alpha", 1.5))
    base = int(wl_cfg.get("base_rows", 12))
    max_rows = int(wl_cfg.get("max_rows", 2000))
    edge_frac = float(wl_cfg.get("edge_case_fraction", 0.10))
    long_len = int(wl_cfg.get("long_string_len", 100_000))

    def resample(n: int) -> pd.DataFrame:
        df = cases.sample(n=n, replace=True, random_state=int(rng.integers(1 << 31)))
        df = df.reset_index(drop=True).copy()
        df["case_id"] = [f"W{i:05d}" for i in range(len(df))]
        return df

    edge_makers = {
        "empty": lambda: cases.iloc[0:0].copy(),
        "single_row": lambda: resample(1),
        "nan_times": lambda: resample(base).assign(t_ai_min=float("nan"),
                                                   t_legacy_min=float("nan")),
        "long_string": lambda: resample(base).assign(source_type="x" * long_len),
        "unicode_string": lambda: resample(base).assign(source_type="пост-мортем ✓\u0000\u202e"),
        "invalid_zero_total": lambda: resample(base).assign(n_total=0, n_misrouted=0),
    }
    edge_names = list(edge_makers)

    # Edge-case slots are chosen without replacement and kinds cycle, so every kind
    # (including the invalid one that must raise) appears whenever n_inputs allows.
    n_edge = min(n_inputs, max(len(edge_names), round(n_inputs * edge_frac)))
    edge_slots = {int(i): edge_names[k % len(edge_names)] for k, i in
                  enumerate(rng.choice(n_inputs, size=n_edge, replace=False))}

    workload: List[Dict[str, Any]] = []
    for idx in range(n_inputs):
        if idx in edge_slots:
            kind = edge_slots[idx]
            df = edge_makers[kind]()
        else:
            n = int(min(max_rows, max(1, round(base * (1 + rng.pareto(alpha))))))
            kind, df = "pareto", resample(n)
        workload.append({"kind": kind, "n_rows": len(df), "cases": df})
    return workload


# --------------------------------------------------------------------------
# Isolated benchmark loop
# --------------------------------------------------------------------------
def _run_once(target_fn: Callable[..., Any], args: Tuple[Any, ...],
              kwargs: Dict[str, Any], phase: str, iteration: int,
              disable_gc: bool) -> Dict[str, Any]:
    """One measurement. Only the call itself sits between the two clock reads."""
    gc.collect()                       # outside the timed region
    if disable_gc:
        gc.disable()
    status, error_type, error_msg = "success", None, None
    c0 = time.process_time_ns()
    t0 = time.perf_counter_ns()
    try:
        target_fn(*args, **kwargs)
    except Exception as e:             # noqa: BLE001 - errors are data, not noise
        status, error_type, error_msg = "error", type(e).__name__, str(e)
    t1 = time.perf_counter_ns()
    c1 = time.process_time_ns()
    if disable_gc:
        gc.enable()
    return {
        "record_type": "run",
        "phase": phase,                # "warmup" | "work"
        "iteration": iteration,
        "latency_ms": (t1 - t0) / 1e6,
        "cpu_ms": (c1 - c0) / 1e6,     # cpu_ms << latency_ms => waiting/noise, not compute
        "status": status,
        "error_type": error_type,
        "error": error_msg,
        "ts_unix_us": time.time_ns() // 1000,   # wall clock, microseconds
        "perf_ns": t1,
    }


def _stats(values_ms: np.ndarray) -> Dict[str, float]:
    return {
        "n": int(len(values_ms)),
        "min_ms": float(values_ms.min()),
        "p50_ms": float(np.percentile(values_ms, 50)),
        "p95_ms": float(np.percentile(values_ms, 95)),
        "p99_ms": float(np.percentile(values_ms, 99)),
        "max_ms": float(values_ms.max()),
        "mean_ms": float(values_ms.mean()),
        "std_ms": float(values_ms.std()),
    }


def summarize_runs(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregates WORK-phase runs only. Errors are counted, never silently dropped."""
    work = [r for r in records if r["phase"] == "work"]
    ok = np.array([r["latency_ms"] for r in work if r["status"] == "success"])
    bad = np.array([r["latency_ms"] for r in work if r["status"] == "error"])
    summary: Dict[str, Any] = {
        "n_work_runs": len(work),
        "n_warmup_runs": sum(r["phase"] == "warmup" for r in records),
        "n_errors": int(len(bad)),
        "error_rate_pct": float(len(bad) / len(work) * 100) if work else float("nan"),
        "n_expected_errors": sum(
            r["phase"] == "work" and r.get("status") == "error" and r.get("expected_error", False)
            for r in records
        ),
        "n_unexpected_errors": sum(
            r["phase"] == "work" and r.get("status") == "error" and not r.get("expected_error", False)
            for r in records
        ),
        "errors_by_type": {},
        "note": "p99 on <1000 successful runs is indicative only.",
    }
    summary["unexpected_error_rate_pct"] = (
        float(summary["n_unexpected_errors"] / len(work) * 100) if work else float("nan")
    )
    for r in work:
        if r["status"] == "error":
            summary["errors_by_type"][r["error_type"]] = \
                summary["errors_by_type"].get(r["error_type"], 0) + 1
    if len(ok):
        summary["success"] = _stats(ok)
        cpu = np.array([r["cpu_ms"] for r in work if r["status"] == "success"])
        summary["success"]["cpu_to_wall_ratio_median"] = float(np.median(cpu / ok))
    if len(bad):
        summary["failed_latency"] = _stats(bad)   # failures kept visible, reported apart
    return summary


def execute_isolated_benchmark(
    target_fn: Callable[..., Any],
    workload: List[Dict[str, Any]],
    make_args: Callable[[Dict[str, Any]], Tuple[Tuple[Any, ...], Dict[str, Any]]],
    warmup_runs: int = 15,
    test_runs: int = 100,
    disable_gc: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Warm-up phase, then an isolated timing loop (no file I/O inside the loop).

    Warm-up runs are recorded with phase="warmup" (errors included) and excluded
    from the summary. Run i uses workload[i % len(workload)].
    """
    if not workload:
        raise ValueError("workload must not be empty")
    records: List[Dict[str, Any]] = []
    for phase, count, offset in (("warmup", warmup_runs, 0), ("work", test_runs, warmup_runs)):
        for i in range(count):
            item = workload[(offset + i) % len(workload)]
            args, kwargs = make_args(item)
            rec = _run_once(target_fn, args, kwargs, phase, i, disable_gc)
            rec["workload_kind"], rec["n_rows"] = item["kind"], item["n_rows"]
            rec["expected_error"] = item["kind"] == "invalid_zero_total"
            records.append(rec)
    return records, summarize_runs(records)


def write_jsonl(path: Path, meta: Dict[str, Any], records: List[Dict[str, Any]]) -> None:
    """All file I/O happens here, after measurement. Line 1 = metadata header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"record_type": "meta", **meta}, ensure_ascii=False) + "\n")
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


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
    lines.append(f"environment={json.dumps(get_system_metadata(cfg))}")
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
        seed = int(cfg["experiment"]["random_seed"])
        warmup = int(bench_cfg.get("warmup_runs", 15))
        runs = int(bench_cfg.get("test_runs", 100))
        workload = build_workload(cases, int(bench_cfg.get("workload", {}).get("n_inputs", 50)),
                                  bench_cfg.get("workload", {}), seed)
        records, agg = execute_isolated_benchmark(
            target_fn=analyze,
            workload=workload,
            make_args=lambda item: ((cfg, item["cases"], agreement), {}),
            warmup_runs=warmup,
            test_runs=runs,
            disable_gc=bool(bench_cfg.get("disable_gc", True)),
        )
        metadata = get_system_metadata(cfg)
        metadata.update({"warmup_runs": warmup, "test_runs": runs,
                         "workload": bench_cfg.get("workload", {}),
                         "disable_gc": bool(bench_cfg.get("disable_gc", True))})
        jsonl_path = Path(bench_cfg.get("output_jsonl", output_dir / "benchmark_runs.jsonl"))
        write_jsonl(jsonl_path, metadata, records)
        (output_dir / "benchmark_summary.json").write_text(
            json.dumps(agg, indent=2), encoding="utf-8")
        print(f"benchmark: {agg['n_work_runs']} work runs (+{agg['n_warmup_runs']} warm-up), "
              f"errors={agg['n_errors']} -> {jsonl_path}")

    if parsed.strict and result["failed_guardrails"]:
        return 2
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())
 
