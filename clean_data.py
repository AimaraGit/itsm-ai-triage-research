import json
from pathlib import Path
import pandas as pd

def parse_and_clean_logs(file_path: str | Path) -> tuple[dict, pd.DataFrame]:
    """Parses raw JSONL logs, filters out warmup runs, and validates clean data."""
    path = Path(file_path)
    metadata = {}
    records = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("record_type") == "meta":
                metadata = entry
            else:
                records.append(entry)

    df = pd.DataFrame(records)
    
    print(f"--- Phase 1 Output ---")
    print(f"Total raw records loaded: {len(df)}")
    
    # --- Phase 2: Warmup Isolation & Filtering ---
    # 1. Filter out warmup records (keep only 'eval' phase)
    eval_df = df[df["phase"] == "eval"].copy()
    
    # 2. Filter out error runs if present
    if "error_type" in eval_df.columns:
        eval_df = eval_df[eval_df["error_type"].isna() | (eval_df["error_type"] == "None")]
        
    print(f"\n--- Phase 2 Output ---")
    print(f"Filtered eval-only records: {len(eval_df)}")
    print(f"Evaluated workload kinds: {eval_df['kind'].unique().tolist()}")
    
    return metadata, eval_df

if __name__ == "__main__":
    meta, clean_df = parse_and_clean_logs("data/raw/test_run.jsonl")
    print("\nClean DataFrame preview:")
    print(clean_df[["phase", "kind", "n_rows", "latency_ms"]])
