import pandas as pd
import numpy as np
from scipy import stats
from clean_data import parse_and_clean_logs

def calculate_nonparametric_metrics(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    aggregated = df.groupby("kind", observed=True)["latency_ms"].agg(
        count="count",
        p50=lambda x: np.percentile(x, 50),
        p95=lambda x: np.percentile(x, 95),
        iqr=lambda x: np.percentile(x, 75) - np.percentile(x, 25)
    ).reset_index()

    legacy_p50 = aggregated.loc[aggregated["kind"] == "legacy", "p50"].values[0]
    aggregated["speedup_vs_legacy"] = legacy_p50 / aggregated["p50"]

    legacy_latencies = df[df["kind"] == "legacy"]["latency_ms"]
    triage_latencies = df[df["kind"] == "ai_triage"]["latency_ms"]

    stat, p_value = stats.mannwhitneyu(legacy_latencies, triage_latencies, alternative="two-sided")
    
    hypothesis_results = pd.DataFrame([{
        "test": "Mann-Whitney U",
        "statistic": stat,
        "p_value": p_value,
        "significant_alpha_0_05": p_value < 0.05
    }])

    return aggregated, hypothesis_results

if __name__ == "__main__":
    meta, clean_df = parse_and_clean_logs("data/raw/test_run.jsonl")
    agg_df, stat_df = calculate_nonparametric_metrics(clean_df)
    
    print("\n--- Phase 3 Output: Aggregated Metrics ---")
    print(agg_df.to_string(index=False))
    
    print("\n--- Statistical Hypothesis Test ---")
    print(stat_df.to_string(index=False))
