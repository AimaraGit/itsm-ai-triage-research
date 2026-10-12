# Methodology Passport Card

## Project information
- **Title:** AI-Enabled Incident Triage and IT Service Management (ITSM)
- **Authors:** Aimara Temresheva, Kirill Dolgopolov
- **GitHub repository:** https://github.com/MagicTMT/itsm-ai-triage-research

## 1. Research type
**Mixed-Methods (qualitative-driven, QUAL -> QUAN).**

- **QUAL component.** Evidence: ITSM architecture blueprints, engineering case studies from Kazakhstani fintech platforms, technical blogs, NBK/AFR regulatory documents and incident post-mortems. Methods: Process-Tracing (structure of AI deployment) and a Document Analysis Protocol (DAP) for coding governance protocols (codebook: `docs/codebook.md`).
- **QUAN component.** Coded observations are converted into indices (1-5 ordinal HITL score, 0-3 governance index, percentage change in handoff time, re-routing rate) and tested with non-parametric tests, implemented in `src/benchmark.py`.
- **Why not a single method.** A pure quantitative experiment is not feasible because raw production logs and server timestamps are proprietary. A pure qualitative description cannot measure velocity gains or test hypotheses.

## 2. Hypotheses
Common rules: one-sided tests, significance level alpha = 0.05, non-parametric tests because scales are ordinal and samples are small. Target sample: >= 10 coded cases per group (C1, C2, E1).

| RQ | H0 (null) | H1 (alternative) | Test (code) |
|---|---|---|---|
| RQ1 Workflow integration | Median HITL embedding score (DV1) of ML-triage cases equals that of legacy rule-based cases. | Median HITL embedding score of ML-triage cases is higher than that of legacy cases (more multi-tier hybrid / human-in-the-loop integration). | Mann-Whitney U, one-sided |
| RQ2 Operational velocity | Median paired difference T_legacy - T_AI in queue-to-queue handoff time is 0 (no change after AI adoption). | Median T_legacy - T_AI > 0: handoff time is shorter after AI adoption (delta T_handoff > 0). Secondary: re-routing rate R_bounce is lower for AI cases than for legacy cases. | Wilcoxon signed-rank (paired); Mann-Whitney U for R_bounce |
| RQ3 Governance & autonomy | Spearman correlation between algorithmic autonomy level (IV2) and governance formalization index (DV4) is 0. | Spearman correlation is positive: higher autonomy goes with more formalized escalation thresholds and fallback protocols. | Spearman rho, one-sided |

## 3. Variable matrix
| Category | Variable | Operationalization and scale | Role |
|---|---|---|---|
| Independent IV1 | Triage mechanism type | Categorical: 0 = legacy rule-based/manual, 1 = ML/AI predictive classifier | Treatment variable (H1, H2) |
| Independent IV2 | Algorithmic autonomy level | Ordinal 1-3: 1 advisory, 2 semi-autonomous (human override), 3 full autonomous. Coded only from statements on who executes the routing action. | Governance driver (H3) |
| Dependent DV1 | Structural integration depth (HITL embedding) | Ordinal 1-5 from the share of hybrid (human + AI) nodes in the support architecture (codebook). Coded only from architecture descriptions. | Outcome of H1 |
| Dependent DV2 | Operational handoff velocity | delta T_handoff = (T_legacy - T_AI) / T_legacy x 100 %, minutes of queue-to-queue transfer | **Primary outcome**, H2 |
| Dependent DV3 | Resolution pathway efficiency | R_bounce = N_misrouted / N_total x 100 % | Secondary outcome, H2 |
| Dependent DV4 | Governance formalization index | I_gov = sum of 3 indicators (documented escalation thresholds, circuit-breaker fallbacks, audit logging), range 0-3. Coded only from governance documents, blind to the IV2 code. | Outcome of H3 |
| Controlled CV1 | System architecture and tech debt | Backend type/age (monolith vs microservices) held comparable within matched pairs | Removes infrastructure noise |
| Controlled CV2 | Regulatory regime | Same NBK/AFR data-isolation requirements for all cases | Prevents regulatory masking of autonomy |
| Controlled CV3 | Incident severity mix | Comparable share of P1-P4 incidents | Controls baseline complexity |
| Controlled CV4 | Coding and computing conditions | Single codebook version, two independent coders for DV1, Python 3.11.9, pinned libraries (requirements.txt), random seed 42, same input CSV | Reproducibility of the pipeline |

## 4. Metrics and baseline
**Primary metric:** delta T_handoff (%) = (T_legacy - T_AI) / T_legacy x 100 - the main indicator that confirms or rejects H1,2 and the overall claim that AI triage improves operations.

**Secondary metrics:** DV1 HITL score (H1), R_bounce (H2), DV4 I_gov (H3).

**Guardrail metrics** (pre-registered; checked by `src/benchmark.py`, output `results/guardrails.csv`):
| ID | Guardrail | Threshold |
|---|---|---|
| G1 | Mean re-routing rate of AI cases (R_bounce) | <= 15 % |
| G2 | Inter-coder agreement on DV1 (quadratic-weighted Cohen's kappa) | >= 0.70 |
| G3 | Share of evidence from independent sources (post-mortems, regulatory filings) - controls publication bias | >= 30 % |
| G4 | Cases with full autonomy (level 3) and no governance protocol (I_gov = 0) | = 0 |

**Baseline (comparison groups):**
- **C1 - legacy baseline:** static keyword routing, manual dispatch or unassisted service desk triage.
- **C2 - vanilla AI baseline:** standalone supervised NLP/LLM classification without fine-tuning, fallback gates or human override.
- **E1 - experimental group:** guardrailed hybrid AI (multi-tier classification, adaptive human escalation thresholds, Kazakh/Russian/English parsing, compliance gates).

## 5. Design and data collection
- **Design:** matched-pair quasi-experimental design with Process-Tracing and Qualitative Comparative Analysis (QCA).
- **Sampling:** fintech platforms in Kazakhstan under the same NBK/AFR regime.
- **Extraction:** standardized Document Analysis Protocol applied to disclosures, public post-mortems, whitepapers and regulatory filings; each case becomes one row in `cases.csv`.
- **Data in the repository:** `data/sample/cases.csv` is synthetic and only checks the pipeline. Real coding is done in Week 7.

## 6. Threats to validity
| Category | Threat | Impact | Mitigation |
|---|---|---|---|
| Internal | Survivorship / publication bias | Companies publish successes and omit failures | Post-mortems, regulatory filings, rollback cases; guardrail G3 |
| Internal | Concurrent infrastructure upgrades | Speed gains attributed to AI instead of refactoring | Process-Tracing to separate AI deployment dates from core-system rewrites |
| Internal | Coder bias | Subjective ordinal coding | Two coders, blind coding of IV2/DV4, guardrail G2 |
| External | Regional regulatory specificity | NBK/AFR rules limit generalization | Regulatory strictness coded as moderating variable in QCA |
| Construct | Metric terminology drift | "MTTR", "automated routing" defined differently | Normalization to codebook definitions |
| Statistical | Small samples, ordinal data | Low power | Non-parametric tests, exact reporting of n, effect direction stated in advance |

## 7. Reproducibility
Run `docker build -t itsm-bench .` then `docker run --rm -v "$(pwd)/results:/app/results" itsm-bench` (see `README.md`). Hypotheses map to code: H1,1 -> `run_tests` Mann-Whitney on `hitl_score`; H1,2 -> Wilcoxon on `t_legacy_min` vs `t_ai_min`; H1,3 -> Spearman `autonomy_level` vs `i_gov`.
