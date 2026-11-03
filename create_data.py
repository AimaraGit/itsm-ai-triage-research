import json
from pathlib import Path

# Create directory if it doesn't exist
Path("data/raw").mkdir(parents=True, exist_ok=True)

# Generate dummy test run data
dummy_data = [
    {"record_type": "meta", "config_sha256": "a1b2c3d4e5f67890", "seed": 42},
    {"phase": "warmup", "kind": "legacy", "n_rows": 100, "latency_ms": 145.2, "error_type": None},
    {"phase": "warmup", "kind": "ai_triage", "n_rows": 100, "latency_ms": 98.4, "error_type": None},
    {"phase": "eval", "kind": "legacy", "n_rows": 500, "latency_ms": 142.1, "error_type": None},
    {"phase": "eval", "kind": "ai_triage", "n_rows": 500, "latency_ms": 85.6, "error_type": None},
    {"phase": "eval", "kind": "ai_triage", "n_rows": 500, "latency_ms": 88.0, "error_type": None},
]

with open("data/raw/test_run.jsonl", "w", encoding="utf-8") as f:
    for row in dummy_data:
        f.write(json.dumps(row) + "\n")

print("Created data/raw/test_run.jsonl")
