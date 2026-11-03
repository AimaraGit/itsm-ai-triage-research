import sys
from pathlib import Path
from clean_data import parse_and_clean_logs
from aggregate_stats import calculate_nonparametric_metrics
from generate_plots import plot_latency_distribution

def main():
    log_file = Path("data/raw/test_run.jsonl")
    if not log_file.exists():
        print(f"Ошибка: Файл {log_file} не найден!")
        sys.exit(1)

    print("=== 1. Ingestion & Cleaning ===")
    metadata, clean_df = parse_and_clean_logs(log_file)

    print("\n=== 2. Aggregation & Statistics ===")
    agg_df, stat_df = calculate_nonparametric_metrics(clean_df)
    print("\nАгрегированные метрики:")
    print(agg_df.to_string(index=False))
    print("\nСтатистический тест (Mann-Whitney U):")
    print(stat_df.to_string(index=False))

    print("\n=== 3. Scientific Plot Generation ===")
    plot_latency_distribution(clean_df, output_path="results/latency_distribution.png")

    print("\n ПАЙПЛАЙН УСПЕШНО ВЫПОЛНЕН!")

if __name__ == "__main__":
    main()
