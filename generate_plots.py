"""Compatibility wrapper for the modular Task 3 visualization functions."""

from src.visualize import plot_latency_distribution, plot_latency_vs_load


if __name__ == "__main__":
    from aggregate_stats import calculate_nonparametric_metrics
    from clean_data import parse_and_clean_logs

    _, clean_df = parse_and_clean_logs("data/raw/test_run.jsonl")
    summary, _ = calculate_nonparametric_metrics(clean_df)
    plot_latency_vs_load(summary)
    plot_latency_distribution(clean_df)
else:
    __all__ = ["plot_latency_distribution", "plot_latency_vs_load"]

