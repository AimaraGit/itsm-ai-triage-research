from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from clean_data import parse_and_clean_logs

def plot_latency_distribution(df, output_path="results/latency_distribution.png"):
    # Настройки стиля для научных публикаций (монохромная совместимость)
    plt.style.use("seaborn-v0_8-paper" if "seaborn-v0_8-paper" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(6, 4), dpi=300)

    # Построение Boxplot с наложением точек (Strip plot)
    sns.boxplot(
        data=df,
        x="kind",
        y="latency_ms",
        palette="Greys",
        width=0.4,
        ax=ax,
        boxprops=dict(alpha=0.7)
    )
    sns.stripplot(
        data=df,
        x="kind",
        y="latency_ms",
        color="black",
        alpha=0.8,
        jitter=0.1,
        size=6,
        ax=ax
    )

    # Оформление осей и заголовков
    ax.set_title("End-to-End Latency Distribution across Workloads", fontsize=11, fontweight="bold")
    ax.set_xlabel("Workload Architecture", fontsize=10)
    ax.set_ylabel("Latency (ms)", fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.5, axis="y")

    # Создание директории и сохранение
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_file, dpi=300)
    plt.close()

    print(f"--- Phase 4 Output ---")
    print(f" Scientific plot successfully saved to: {out_file.resolve()}")

if __name__ == "__main__":
    meta, clean_df = parse_and_clean_logs("data/raw/test_run.jsonl")
    plot_latency_distribution(clean_df)
