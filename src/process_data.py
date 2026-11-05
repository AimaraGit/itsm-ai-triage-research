"""Load, validate, and summarize benchmark JSONL logs."""

import argparse
import json
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

import numpy as np
import pandas as pd

EVALUATION_PHASES = {"work", "benchmark", "eval", "evaluation"}
REQUIRED_RUN_FIELDS = {"phase", "latency_ms", "status", "workload_kind", "n_rows"}


def load_benchmark_data(path: Path) -> Tuple[Dict, pd.DataFrame]:
    """Load a metadata-headed JSONL file and return evaluation runs only.

    Warm-up rows are excluded from analysis, while failed evaluation rows remain
    available for the error-rate guardrail.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Benchmark JSONL not found: {path}")

    metadata = None
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Expected a JSON object on line {line_number} of {path}")
            if record.get("record_type") == "meta":
                if metadata is not None or records:
                    raise ValueError("The metadata record must appear exactly once, before run records")
                metadata = record
            elif record.get("record_type") == "run":
                records.append(record)
            else:
                raise ValueError(f"Unknown record_type on line {line_number}: {record.get('record_type')!r}")

    if metadata is None:
        raise ValueError("Benchmark JSONL is missing its metadata header")
    if not records:
        raise ValueError("Benchmark JSONL contains no run records")

    frame = pd.DataFrame(records)
    missing = REQUIRED_RUN_FIELDS - set(frame.columns)
    if missing:
        raise ValueError(f"Benchmark run records are missing fields: {sorted(missing)}")
    if not frame["phase"].isin(EVALUATION_PHASES | {"warmup"}).all():
        unknown = sorted(set(frame["phase"]) - EVALUATION_PHASES - {"warmup"})
        raise ValueError(f"Unsupported benchmark phases: {unknown}")
    if not frame["status"].isin({"success", "error"}).all():
        raise ValueError("Run status must be either 'success' or 'error'")

    for column in ("latency_ms", "n_rows"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if not np.isfinite(frame["latency_ms"]).all() or (frame["latency_ms"] < 0).any():
        raise ValueError("latency_ms values must be finite and non-negative")
    if not np.isfinite(frame["n_rows"]).all() or (frame["n_rows"] < 0).any():
        raise ValueError("n_rows values must be finite and non-negative")
    if not np.equal(frame["n_rows"], np.floor(frame["n_rows"])).all():
        raise ValueError("n_rows values must be integers")
    frame["n_rows"] = frame["n_rows"].astype(int)

    if "expected_error" not in frame:
        frame["expected_error"] = (
            frame["workload_kind"].eq("invalid_zero_total")
            & frame["status"].eq("error")
        )
    elif not frame["expected_error"].dropna().isin({True, False}).all():
        raise ValueError("expected_error values must be booleans")
    else:
        frame["expected_error"] = frame["expected_error"].fillna(False).astype(bool)

    warmup_count = int(frame["phase"].eq("warmup").sum())
    evaluation = frame.loc[frame["phase"].isin(EVALUATION_PHASES)].copy()
    if evaluation.empty:
        raise ValueError("Benchmark JSONL contains no evaluation runs")

    metadata = dict(metadata)
    metadata.update({
        "n_raw_runs": len(frame),
        "n_warmup_runs": warmup_count,
        "n_evaluation_runs": len(evaluation),
    })
    evaluation["throughput_rows_s"] = np.where(
        evaluation["status"].eq("success")
        & evaluation["latency_ms"].gt(0)
        & evaluation["n_rows"].gt(0),
        evaluation["n_rows"] / (evaluation["latency_ms"] / 1000.0),
        np.nan,
    )
    return metadata, add_outlier_flags(add_load_bins(evaluation))


def add_load_bins(frame: pd.DataFrame, bins: int = 5) -> pd.DataFrame:
    """Add deterministic quantile bins for workload size without dropping rows."""
    out = frame.copy()
    unique_sizes = int(out["n_rows"].nunique())
    if unique_sizes < 2:
        out["load_bin"] = 1
    else:
        out["load_bin"] = (
            pd.qcut(
                out["n_rows"],
                q=min(max(1, bins), unique_sizes),
                labels=False,
                duplicates="drop",
            )
            .astype("Int64")
            .add(1)
        )
    return out


def add_outlier_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """Flag, but never remove, latency outliers within workload-size bins."""
    out = frame.copy()
    out["latency_outlier"] = False
    successful = out.loc[out["status"].eq("success")]
    for _, group in successful.groupby(["workload_kind", "load_bin"], dropna=False):
        if len(group) < 4:
            continue
        q1, q3 = group["latency_ms"].quantile([0.25, 0.75])
        spread = q3 - q1
        mask = (
            (group["latency_ms"] < q1 - 1.5 * spread)
            | (group["latency_ms"] > q3 + 1.5 * spread)
        )
        out.loc[group.index[mask], "latency_outlier"] = True
    return out


def bootstrap_ci(
    values: Iterable[float],
    statistic: Callable[[np.ndarray], float] = np.median,
    confidence: float = 0.95,
    resamples: int = 2000,
    seed: int = 42,
) -> Tuple[float, float]:
    """Return a seeded percentile-bootstrap confidence interval."""
    sample = np.asarray(list(values), dtype=float)
    sample = sample[np.isfinite(sample)]
    if not len(sample):
        return float("nan"), float("nan")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    if resamples < 1:
        raise ValueError("resamples must be positive")
    if len(sample) == 1:
        value = float(statistic(sample))
        return value, value

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(sample), size=(resamples, len(sample)))
    estimates = np.asarray([statistic(sample[index]) for index in indices])
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(estimates, [tail, 1.0 - tail])
    return float(low), float(high)


def _summarize_group(
    frame: pd.DataFrame,
    workload_kind: str,
    load_bin: int,
    bootstrap_samples: int,
    seed: int,
) -> Dict:
    successful = frame.loc[frame["status"].eq("success")]
    failed = frame.loc[frame["status"].eq("error")]
    latency = successful["latency_ms"].to_numpy(dtype=float)
    throughput = successful["throughput_rows_s"].dropna().to_numpy(dtype=float)
    row = {
        "workload_kind": workload_kind,
        "load_bin": load_bin,
        "n_runs": int(len(frame)),
        "n_success": int(len(successful)),
        "n_errors": int(len(failed)),
        "n_expected_errors": int(failed["expected_error"].sum()),
        "n_unexpected_errors": int((~failed["expected_error"]).sum()),
        "error_rate_pct": 100.0 * len(failed) / len(frame) if len(frame) else np.nan,
        "unexpected_error_rate_pct": (
            100.0 * int((~failed["expected_error"]).sum()) / len(frame) if len(frame) else np.nan
        ),
        "n_outliers_flagged": int(successful["latency_outlier"].sum()),
        "n_rows_min": int(frame["n_rows"].min()),
        "n_rows_median": float(frame["n_rows"].median()),
        "n_rows_max": int(frame["n_rows"].max()),
    }

    metrics = {
        "latency_mean_ms": np.mean,
        "latency_sd_ms": lambda values: np.std(values, ddof=1) if len(values) > 1 else 0.0,
        "latency_p25_ms": lambda values: np.percentile(values, 25),
        "latency_p50_ms": lambda values: np.percentile(values, 50),
        "latency_p75_ms": lambda values: np.percentile(values, 75),
        "latency_p95_ms": lambda values: np.percentile(values, 95),
        "latency_p99_ms": lambda values: np.percentile(values, 99),
    }
    for name, function in metrics.items():
        row[name] = float(function(latency)) if len(latency) else np.nan
    for percentile in (50, 95, 99):
        low, high = bootstrap_ci(
            latency,
            statistic=lambda values, p=percentile: float(np.percentile(values, p)),
            resamples=bootstrap_samples,
            seed=seed + percentile + load_bin,
        )
        row[f"latency_p{percentile}_ci95_low_ms"] = low
        row[f"latency_p{percentile}_ci95_high_ms"] = high

    row["throughput_mean_rows_s"] = float(np.mean(throughput)) if len(throughput) else np.nan
    row["throughput_p50_rows_s"] = float(np.median(throughput)) if len(throughput) else np.nan
    low, high = bootstrap_ci(
        throughput, resamples=bootstrap_samples, seed=seed + 500 + load_bin
    )
    row["throughput_p50_ci95_low_rows_s"] = low
    row["throughput_p50_ci95_high_rows_s"] = high
    return row


def aggregate_metrics(
    evaluation_runs: pd.DataFrame,
    bootstrap_samples: int = 2000,
    seed: int = 42,
    max_unexpected_error_rate_pct: float = 0.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Summarize evaluation runs and return a separate error-rate guardrail table."""
    if evaluation_runs.empty:
        raise ValueError("Cannot summarize an empty evaluation dataset")
    required = REQUIRED_RUN_FIELDS | {"expected_error", "latency_outlier", "load_bin"}
    missing = required - set(evaluation_runs.columns)
    if missing:
        raise ValueError(f"Evaluation data is missing processed fields: {sorted(missing)}")
    if not 0 <= max_unexpected_error_rate_pct <= 100:
        raise ValueError("max_unexpected_error_rate_pct must be between 0 and 100")

    rows = []
    for index, ((kind, load_bin), group) in enumerate(
        evaluation_runs.groupby(["workload_kind", "load_bin"], sort=True, dropna=False)
    ):
        rows.append(
            _summarize_group(
                group, str(kind), int(load_bin), bootstrap_samples, seed + index * 1000
            )
        )
    rows.append(_summarize_group(
        evaluation_runs, "ALL", 0, bootstrap_samples, seed + 999_999
    ))
    summary = pd.DataFrame(rows)

    all_runs = evaluation_runs
    errors = all_runs.loc[all_runs["status"].eq("error")]
    unexpected_rate = (
        100.0 * int((~errors["expected_error"]).sum()) / len(all_runs)
        if len(all_runs)
        else np.nan
    )
    guardrails = pd.DataFrame([{
        "guardrail": "Unexpected evaluation error rate (%)",
        "value": unexpected_rate,
        "expected_errors_excluded_from_guardrail": int(errors["expected_error"].sum()),
        "total_evaluation_runs": int(len(all_runs)),
        "unexpected_errors": int((~errors["expected_error"]).sum()),
        "threshold_pct": float(max_unexpected_error_rate_pct),
        "passed": bool(unexpected_rate <= max_unexpected_error_rate_pct),
        "note": "Expected invalid_zero_total edge-case errors remain counted in error_rate_pct.",
    }])
    return summary, guardrails


def process_jsonl(
    input_path: Path,
    output_dir: Path = Path("data/processed"),
    bootstrap_samples: int = 2000,
    seed: int = 42,
    max_unexpected_error_rate_pct: float = 0.0,
) -> Tuple[Dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the complete data-processing stage and write reproducible CSV outputs."""
    metadata, evaluation = load_benchmark_data(input_path)
    summary, guardrails = aggregate_metrics(
        evaluation, bootstrap_samples, seed, max_unexpected_error_rate_pct
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_dir / "metrics_summary.csv", index=False, float_format="%.8g")
    guardrails.to_csv(output_dir / "benchmark_guardrails.csv", index=False, float_format="%.8g")
    return metadata, evaluation, summary, guardrails


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Process ITSM benchmark JSONL logs")
    parser.add_argument("--input", type=Path, default=Path("data/raw/test_run.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-unexpected-error-rate-pct", type=float, default=0.0)
    args = parser.parse_args(argv)
    metadata, evaluation, summary, guardrails = process_jsonl(
        args.input, args.output_dir, args.bootstrap_samples, args.seed,
        args.max_unexpected_error_rate_pct,
    )
    print(
        f"Loaded {metadata['n_raw_runs']} runs; excluded {metadata['n_warmup_runs']} warm-ups; "
        f"summarized {metadata['n_evaluation_runs']} evaluation runs."
    )
    print(f"Flagged {int(evaluation['latency_outlier'].sum())} latency outliers without removing them.")
    print(summary.tail(1).to_string(index=False))
    print(guardrails.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
