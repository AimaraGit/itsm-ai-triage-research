# AI-Enabled Incident Triage and IT Service Management (ITSM)

**Authors:** Aimara Temresheva, Kirill Dolgopolov  
**Course:** Research Methods (SCOM3001), Tasks 2–4  
**License:** MIT

## Research question

How are AI-enabled incident triage mechanisms integrated into ITSM workflows (RQ1), how do they change operational handoff velocity and resolution pathways (RQ2), and how are human escalation protocols structured relative to algorithmic autonomy (RQ3) in Kazakhstani fintech environments?

## Overview

This mixed-methods (qualitative-driven) study codes public engineering disclosures, post-mortems, and regulatory documents using the Document Analysis Protocol in [`docs/codebook.md`](docs/codebook.md). The research pipeline computes HITL, handoff-time, misrouting, and governance measures, tests H1.1–H1.3, and evaluates the registered study guardrails.

> **Data provenance and interpretation:** The **12 coded C1/C2/E1 cases** in `data/sample/cases.csv` were assembled from **publicly available real-world incident reports, engineering publications, and research case studies**, mapped in [`docs/data_sources.md`](docs/data_sources.md). They are **secondary-source case codings**, not 12 raw incident tickets collected directly from organizations. Several values are analyst-assigned proxies, normalized counts, or illustrative before/after times; these MUST NOT be represented as exact measured company-level figures unless verified in the cited source. The separate `data/raw/test_run.jsonl` contains **real observed execution-time measurements** of the Python analysis pipeline using **generated benchmark workloads**, not production ITSM latency.

## Results and discussion (Tasks 3–4)

The earlier Task 3 draft is [`reports/paper_section_4.md`](reports/paper_section_4.md); its numerical results may refer to an older run and should not be treated as the source of truth for the current benchmark.

### C1 baseline vs E1 proposed method (real-world-source-based case codings)

The `data/sample/cases.csv` file comprises **12 case-level codings sourced from real-world publications** (four C1, four C2, four E1). See the [case-to-source traceability table](docs/data_sources.md) for the organizations, references, and provenance caveats. **Case-level metric numbers are not all directly reported in the cited publications**: in particular, denominators such as `100`, inferred misrouting counts, HITL scores, governance flags, and illustrative time pairs may be coding conventions or proxy values. They should be treated as **source-informed illustrative data**, rather than raw production ticket-level measurements. The results below are descriptive summaries of those coded values, not causal estimates.

| Metric (case-level mean) | Legacy C1 (n=4) | Standalone AI C2 (n=4) | Hybrid E1 (n=4) |
|---|---:|---:|---:|
| HITL score (1–5) | 1.50 | 2.75 | 4.25 |
| Handoff reduction (%) | N/A | 18.67 | 55.98 |
| Misrouting rate (%) | approx. 18.0 | 15.25 | 5.00 |
| Governance index (0–3) | 1.25 | 1.75 | 3.00 |

The handoff reduction shown here is the **mean of four case-level percentage reductions in each AI group**, not necessarily the percentage reduction between the group-mean times. The C1 cases have no paired time data. These three groups combine heterogeneous organizations and publications; they are not a matched controlled experiment. Do not interpret descriptive differences or the corresponding p-values as causal proof that one routing strategy outperforms another.

**Coder agreement:** `data/sample/coder_agreement.csv` contains 12 paired coder labels (10 exact matches; 83.33% raw agreement). Weighted kappa can be computed from these labels; this alone does not establish that two independent human annotators performed the coding. The documentation must state who assigned each label and how disagreements were adjudicated before claiming independent inter-rater validation.

**Guardrails:** Recompute G1–G4 from the current case file. In particular, do not reuse the historical v1.0 claim that all four pass: on the updated case labels the independent-evidence G3 result was 25%, below its 30% threshold. This guardrail describes the coding dataset, not independently confirmed field evidence.

### Updated local analysis-pipeline profile (measured runtime; generated inputs)

The updated checked-in JSONL records actual execution-time measurements of a synchronous `analyze()` call over 100 evaluation runs on programmatically generated workloads. There were 98 successful runs and 2 expected invalid-input failures (2% evaluation error rate; 0 unexpected errors). For successful runs, the updated overall latency is approximately **12.47 ms median, 19.24 ms p95, and 21.42 ms p99**. The log records Python 3.11.9, Linux, AMD EPYC 7763, a fixed random seed of 42, and 15 warm-up runs excluded from evaluation. These are measurements of research software, not production ITSM service performance; upper percentiles are indicative with this sample size. Environment details and every run are in [`data/raw/test_run.jsonl`](data/raw/test_run.jsonl), and the aggregate table is [`data/processed/metrics_summary.csv`](data/processed/metrics_summary.csv).

![Latency percentiles versus input size](reports/figures/fig1_latency_vs_load.png)

**Figure 1.** Latency percentiles by input size in cases per analysis call. Shaded bands are 95% percentile-bootstrap confidence intervals. The benchmark does not control offered request rate, so the x-axis is not RPS.

![Latency distribution by workload shape](reports/figures/fig2_distribution_boxplot.png)

**Figure 2.** Measured successful-run latency by programmatically generated workload shape. Boxes show p25–p75, whiskers 1.5×IQR, and diamonds show the median with a 95% bootstrap confidence interval. Failed runs are retained in the guardrail summary.

Vector exports: [Figure 1 PDF](reports/figures/fig1_latency_vs_load.pdf) · [Figure 2 PDF](reports/figures/fig2_distribution_boxplot.pdf)

### Interpretation and limitations

The timing experiment measures the local Python data-analysis function, not a deployed ITSM system. It has no controlled request-rate schedule, concurrency, network latency, or second runtime implementation. Consequently it cannot substantiate a baseline-versus-proposed **latency** claim; the C1/E1 table above is a synthetic research-metric example only. A production comparison requires representative de-identified data, controlled load, a measured baseline implementation, and a predeclared experimental protocol.

### Domain model (ML/AI track)

The formal domain artifact for the ML/AI track (loss function, target metrics, guardrail definitions, and a notation table, in LaTeX) is in [`docs/domain_model.md`](docs/domain_model.md).

## Reproducible pipeline

Use Python 3.11 or 3.12 with the pinned dependencies (Python 3.13+ is not supported by the pinned numpy 1.26.4), then run from the repository root:

```bash
python -m pip install -r requirements.txt
python run_pipeline.py --config configs/config.yaml
```

The command runs the configured benchmark, writes `data/raw/test_run.jsonl`, excludes warm-up records during processing while retaining failures, creates:

- `data/processed/metrics_summary.csv`
- `data/processed/benchmark_guardrails.csv`
- `reports/figures/fig1_latency_vs_load.pdf` and `.png` (300 DPI)
- `reports/figures/fig2_distribution_boxplot.pdf` and `.png` (300 DPI)

To reprocess the existing raw log without measuring again:
> Re-running without `--skip-benchmark` measures latency again and overwrites `data/raw/test_run.jsonl`; absolute latency values depend on the machine, so the numbers in this README correspond to the committed log.

```bash
python run_pipeline.py --config configs/config.yaml --skip-benchmark
```

The notebook [`notebooks/01_data_analysis.ipynb`](notebooks/01_data_analysis.ipynb) contains the same steps and saved outputs. From the repository root, select the Python 3.11/3.12 environment and use **Kernel → Restart & Run All**.

The Docker image runs the same pipeline:

```bash
docker build -t itsm-bench .
docker run --rm -v "$(pwd)/data:/app/data" -v "$(pwd)/reports:/app/reports" -v "$(pwd)/results:/app/results" itsm-bench
```
In GitHub Codespaces or other remote Docker environments, bind mounts may not work. Copy the outputs out of the container instead:

```bash
docker build -t itsm-bench .
docker run --name bench itsm-bench
docker cp bench:/app/data/. ./data/ && docker cp bench:/app/reports/. ./reports/ && docker rm bench
```

## Repository structure

```text
.
├── README.md
├── LICENSE
├── Dockerfile
├── requirements.txt                    # exact version pins
├── run_pipeline.py                     # entry point: benchmark -> processing -> figures
├── .gitignore                          # excludes checkpoints, caches, virtual environments
├── .dockerignore
├── configs/config.yaml
├── data/
│   ├── raw/test_run.jsonl
│   ├── processed/metrics_summary.csv
│   └── sample/                         # 12 source-informed coded cases and coder-agreement labels
├── docs/
│   ├── codebook.md
│   ├── data_sources.md                 # case-to-source traceability and metric caveats
│   ├── methodology_card.md
│   └── domain_model.md                 # ML/AI track: loss, metrics, notation (LaTeX)
├── notebooks/01_data_analysis.ipynb
├── reports/
│   ├── paper_section_4.md              # LMS-ready results section
│   └── figures/                        # PDF and 300-DPI PNG exports
├── src/
│   ├── benchmark.py                    # data-analysis benchmark and Task 2 pipeline
│   ├── metrics.py                      # research outcome formulas
│   ├── process_data.py                 # JSONL validation and aggregation
│   └── visualize.py                    # publication-ready figures
└── tests/test_pipeline.py
```

## Planned research benchmarks

| ID | Hypothesis | Variable(s) | Method | Status |
|---|---|---|---|---|
| B1 | H1.1 | DV1 HITL score, ML vs legacy | Mann–Whitney U (one-sided) | Source-informed case analysis; source-level metric validation required |
| B2 | H1.2 (primary) | DV2 handoff-time reduction | Wilcoxon signed-rank (paired) | Pipeline ready; real data required |
| B3 | H1.2 (secondary) | DV3 misrouting rate | Mann–Whitney U (one-sided) | Pipeline ready; real data required |
| B4 | H1.3 | IV2 autonomy vs DV4 governance | Spearman rho (one-sided) | Pipeline ready; real data required |
| G1–G4 | Study guardrails | Misrouting, coder agreement, source share, autonomy/governance | Pre-registered threshold checks | Pipeline ready; real data required |

## Citation

```bibtex
@misc{temresheva2026itsm,
  title  = {AI-Enabled Incident Triage and IT Service Management (ITSM)},
  author = {Temresheva Aimara and Dolgopolov Kirill},
  year   = {2026},
  howpublished = {\url{https://github.com/AimaraGit/itsm-ai-triage-research}}
}
```

Released under the MIT License (see [`LICENSE`](LICENSE)).
