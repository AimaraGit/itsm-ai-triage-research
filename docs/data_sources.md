# Sources and provenance of coded cases (Task 4)

## Scope and interpretation

The current `data/sample/cases.csv` contains **12 source-informed research codings** (C1, C2, E1, four cases each) assembled from published real incident reports and technical research. The publications are real sources; the CSV is **not** a raw export of original incident tickets from Cloudflare, Microsoft, Uber, or other organizations. Several paper-level outcomes are not provided at the exact per-case granularity encoded in the CSV. **Any value lacking an exact source locator or methodological derivation must be classified as an analyst-derived proxy / illustrative normalization, not as an observed company statistic.**

The published cases are cross-organization examples, mostly outside Kazakhstan. They therefore cannot independently demonstrate operational effects in *Kazakhstani fintech*. Additionally, the groups are neither randomized nor matched by severity, workload, team, or platform.

## Case-to-source traceability

| ID | Group | Organization / case | Source | Important provenance/measurement caveat |
|---|---|---|---|---|
| S01 | C1 | Cloudflare, 1.1.1.1 resolver incident (14 Jul 2025) | [Cloudflare incident write-up](https://blog.cloudflare.com/cloudflare-1-1-1-1-incident-on-july-14-2025/) | The reported ~23% concerns edge servers whose IP bindings were removed; it is **not** an ITSM misrouting rate. `23/100` is a proxy transformation. |
| S02 | C1 | Microsoft research on cloud incidents (2025) | [arXiv:2504.08865v2](https://arxiv.org/html/2504.08865v2) | The claimed `20/140` routing error denominator and correspondence to the cited study need a pinpoint citation. |
| S03 | C1 | SEC Form 8-K incident disclosure | [Practitioner walkthrough](https://www.finrep.ai/blog/item-1-05-form-8-k-cybersecurity-disclosure-2026-practitioner-walkthrough) | This URL is a **third-party walkthrough, not an actual SEC regulatory filing**. The asserted `22/120` misrouting count needs independent evidence. |
| S04 | C1 | Cloudflare 2025 outage postmortem | [iLert postmortem archive](https://www.ilert.com/postmortems/cloudflare-global-outage-nov-2025) | Secondary postmortem description; `18/110` ITSM misrouting ratio is not independently established here. |
| S05 | C2 | Uber COTA v1 | [Uber Engineering COTA](https://www.uber.com/us/en/blog/cota/) | The values `50→45 min` and `15/100` must be checked against the publication, not inferred from an overall percentage. |
| S06 | C2 | Uber COTA v2 | [Uber Engineering COTA v2](https://www.uber.com/us/en/blog/cota-v2/) | The values `45→42 min` and `14/100` need source-level verification. |
| S07 | C2 | Microsoft DeepCT | [Microsoft Research DeepCT](https://www.microsoft.com/en-us/research/publication/continuous-incident-triage-for-large-scale-online-service-systems/) | Verify whether 86% is *hop accuracy* vs an ITSM ticket-level misrouting rate; `60→42 min` needs documentation. |
| S08 | C2 | Microsoft TRIANGLE, Team B | [TRIANGLE paper](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/02/TRIANGLE_ASE25-1.pdf) | Confirm team-specific 82% and `50→36 min` in the paper; do not convert aggregate accuracy into a measured misrouting count without basis. |
| S09 | E1 | Microsoft TRIANGLE, Team A | [TRIANGLE paper](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/02/TRIANGLE_ASE25-1.pdf) | Verify team-specific 92%, HITL/guardrail interpretation, and `50→41 min`. |
| S10 | E1 | Microsoft TRIANGLE, Team F | [Microsoft Research TRIANGLE](https://www.microsoft.com/en-us/research/publication/triangle-empowering-incident-triage-with-multi-agents/) | Publication reports *up to* 97% accuracy and *up to* 91% TTE reduction across its study. These maxima do not by themselves prove the exact Team F pair `55→5 min` or `3/100`. |
| S11 | E1 | Microsoft TRIANGLE, Teams C/E | [TRIANGLE code repository](https://github.com/microsoft/Triangle) | Verify team-level consensus, 96% accuracy and `60→27 min`; a repository link alone may not support these measurements. |
| S12 | E1 | Writer Cerebro / UiPath | [Writer Cerebro](https://writer.com/engineering/cerebro-ai-security-alert-triage-system/) | Combines **two organizations in one case** while only linking the Writer source; the 95% and `45→18 min` need source-level evidence. |

## Coded variables

- `group`: comparative treatment-category assignment based on qualitative interpretation of source.
- `source_type`: broad document category, **not proof of primary-source status**. For S03, the current `regulatory_filing` label should be revised or supported by an actual SEC filing.
- `hitl_score`, `autonomy_level`, `esc_thresholds`, `circuit_breaker`, `audit_logging`: document-derived research coding decisions; these require a written coding rubric and locators in the original text.
- `n_misrouted`, `n_total`: ratios in `cases.csv`; some values normalize reported accuracy or describe **different phenomena**, so do not call all of them measured ticket misrouting rates.
- `t_legacy_min`, `t_ai_min`: illustrative paired quantities where source does not publish exact matched measurements. Keep missing C1 entries missing; no imputation.
- `coder_agreement.csv`: 12 paired labels with 10 exact matches (83.33%). These figures describe a *file*, not proof of independent human labeling.

## Distinct benchmark dataset

`data/raw/test_run.jsonl` measures actual Python `analyze()` execution times on generated workloads. The current log records Python 3.11.9, Linux, AMD EPYC 7763, seed 42, 15 warm-up iterations, 100 test iterations, 98 successes, and two expected invalid-input errors. These measurements are not production incident-triage times. Figures `fig1_latency_vs_load` and `fig2_distribution_boxplot` should be linked to this current log, rather than to the old `v1.0` benchmark.

## Verification checklist before publishing empirical claims

1. Add an exact section/page/table locator for each numeric claim in S01–S12 and record original units and denominators.
2. Mark each CSV outcome as **directly reported**, **derived from an explicitly reported number**, or **analyst-assigned proxy**.
3. Use the same unit of analysis across cases or clearly call the analysis an exploratory comparison of heterogeneous publications.
4. Declare who performed coding, whether coders were independent, and how disagreements were resolved.
5. Recompute all main-paper group metrics, hypotheses, guardrails, figures, and captions against the committed CSVs.
