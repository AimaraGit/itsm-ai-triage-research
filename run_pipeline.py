"""Run the benchmark, process its logs, and export Task 3 figures."""

import argparse
from pathlib import Path
from typing import Optional

import yaml

from src import benchmark
from src.process_data import process_jsonl
from src.visualize import generate_figures


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full ITSM Task 3 pipeline")
    parser.add_argument("--config", type=Path, default=Path("configs/config.yaml"))
    parser.add_argument(
        "--skip-benchmark",
        action="store_true",
        help="process an existing JSONL log without generating a new benchmark run",
    )
    args = parser.parse_args(argv)
    if not args.config.is_file():
        raise FileNotFoundError(f"Config file not found: {args.config}")

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    benchmark_config = config.get("benchmark", {})
    input_path = Path(benchmark_config.get("output_jsonl", "data/raw/test_run.jsonl"))
    bootstrap_samples = int(benchmark_config.get("bootstrap_samples", 2000))
    seed = int(config["experiment"]["random_seed"])

    if not args.skip_benchmark:
        exit_code = benchmark.main(["--config", str(args.config)])
        if exit_code:
            return exit_code

    metadata, evaluation, summary, guardrails = process_jsonl(
        input_path,
        Path(config["paths"].get("processed_dir", "data/processed")),
        bootstrap_samples,
        seed,
        float(benchmark_config.get("max_unexpected_error_rate_pct", 0.0)),
    )
    figure_paths = generate_figures(
        evaluation,
        summary,
        Path(config["paths"].get("figures_dir", "reports/figures")),
        bootstrap_samples,
        seed,
    )
    print(
        f"Processed {metadata['n_evaluation_runs']} evaluation runs "
        f"({metadata['n_warmup_runs']} warm-ups excluded)."
    )
    print(guardrails.to_string(index=False))
    for pair in figure_paths:
        print(f"Saved {pair[0]} and {pair[1]}")
    return 0 if bool(guardrails["passed"].all()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
