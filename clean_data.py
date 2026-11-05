from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

from src.process_data import load_benchmark_data


def parse_and_clean_logs(file_path: str | Path) -> Tuple[Dict, pd.DataFrame]:
    """Load evaluation records, excluding warm-up while retaining failed runs."""
    metadata, evaluation = load_benchmark_data(Path(file_path))
    print(f"Raw runs loaded: {metadata['n_raw_runs']}")
    print(f"Warm-up runs excluded: {metadata['n_warmup_runs']}")
    print(f"Evaluation runs retained: {metadata['n_evaluation_runs']}")
    print(f"Evaluation errors retained: {int(evaluation['status'].eq('error').sum())}")
    return metadata, evaluation


if __name__ == "__main__":
    _, clean_df = parse_and_clean_logs("data/raw/test_run.jsonl")
    print(clean_df.head().to_string(index=False))

