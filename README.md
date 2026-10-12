# AI-Enabled Incident Triage and IT Service Management (ITSM)

**Authors:** Aimara Temresheva, Kirill Dolgopolov
**Course:** Research Methods (SCOM3001), Task 2 - Methodology Card and Research Repository
**License:** MIT

## Research Question
How are AI-enabled incident triage mechanisms integrated into ITSM workflows (RQ1), how do they change operational handoff velocity and resolution pathways (RQ2), and how are human escalation protocols structured relative to algorithmic autonomy (RQ3) in Kazakhstani fintech environments?

## Overview
Mixed-methods (qualitative-driven) study. Public engineering disclosures, post-mortems and regulatory documents are coded with a Document Analysis Protocol (`docs/codebook.md`). This repository contains the **measurement tool** that turns coded cases into indices (HITL score, delta T_handoff, R_bounce, governance index), tests H1.1-H1.3 with non-parametric tests and checks four guardrail metrics. The full design is in `docs/methodology_card.md`.

> `data/sample/` is a **synthetic placeholder** used only to verify that the pipeline runs. Its output is not evidence. Real data collection starts in Week 7.

## Repository structure
```text
.
├── README.md
├── LICENSE
├── Dockerfile
├── requirements.txt          # exact pins
├── configs/config.yaml       # paths, groups, alpha, guardrail thresholds, seed
├── data/
│   ├── README.md
│   └── sample/               # cases.csv (12 rows), coder_agreement.csv
├── src/
│   ├── benchmark.py          # pipeline entry point
│   └── metrics.py            # formulas (dT_handoff, R_bounce, I_gov, kappa)
├── tests/test_pipeline.py    # unit + end-to-end tests
├── docs/
│   ├── methodology_card.md
│   └── codebook.md
├── notebooks/                # exploratory analysis (Week 7+)
└── results/                  # generated outputs (git-ignored)
```

## System requirements
- Docker >= 24 **or** Python 3.11+ with `pip`
- Any OS (Linux, macOS, Windows), 1 GB RAM is enough; no GPU needed

## Quickstart (3 commands)
```bash
git clone https://github.com/MagicTMT/itsm-ai-triage-research.git && cd itsm-ai-triage-research
docker build -t itsm-bench .          # also runs the unit tests
docker run --rm -v "$(pwd)/results:/app/results" itsm-bench
```
Results appear in `results/`: `metrics.csv`, `hypothesis_tests.csv`, `guardrails.csv`, `run.log`.

Without Docker:
```bash
pip install -r requirements.txt && python -m src.benchmark --config configs/config.yaml
```

## Planned benchmarks
| ID | Hypothesis | Variable(s) | Method | Status |
|---|---|---|---|---|
| B1 | H1.1 | DV1 HITL score, ML vs legacy | Mann-Whitney U (one-sided) | pipeline ready; real data Week 7 |
| B2 | H1.2 (primary) | DV2 delta T_handoff | Wilcoxon signed-rank (paired) | pipeline ready; real data Week 7 |
| B3 | H1.2 (secondary) | DV3 R_bounce | Mann-Whitney U (one-sided) | pipeline ready; real data Week 7 |
| B4 | H1.3 | IV2 autonomy vs DV4 I_gov | Spearman rho (one-sided) | pipeline ready; real data Week 7 |
| G1-G4 | Guardrails | bounce rate, kappa, source share, autonomy without governance | threshold checks | pipeline ready |

## Citation
```bibtex
@misc{temresheva2026itsm,
  title  = {AI-Enabled Incident Triage and IT Service Management (ITSM)},
  author = {Temresheva, Aimara and Dolgopolov, Kirill},
  year   = {2026},
  howpublished = {\url{https://github.com/MagicTMT/itsm-ai-triage-research}}
}
```
Released under the MIT License (see `LICENSE`).
