# Codebook (Document Analysis Protocol, DAP)

One row of `cases.csv` = one coded case (a company disclosure, post-mortem or regulatory filing).

| Column | Variable | Values / rule |
|---|---|---|
| `case_id` | identifier | unique string |
| `group` | study group | `C1` legacy baseline, `C2` vanilla AI baseline, `E1` guardrailed hybrid AI |
| `source_type` | evidence type | `engineering_blog`, `postmortem`, `regulatory_filing`, ... |
| `triage_type` | **IV1** | 0 = legacy rule-based/manual, 1 = ML/AI predictive classifier |
| `autonomy_level` | **IV2** | 1 = advisory, 2 = semi-autonomous (human override), 3 = full autonomous |
| `hitl_score` | **DV1** | 1-5 ordinal: 1 = no human checkpoint; 2 = single manual review step; 3 = human override exists but is not tiered; 4 = tiered human checkpoints at some queue levels; 5 = human checkpoints embedded at every tier with defined hand-back rules (approx. share of hybrid nodes among all nodes: <=10%, 11-30%, 31-50%, 51-75%, >75% in the architecture blueprint) |
| `t_legacy_min`, `t_ai_min` | **DV2** inputs | disclosed queue-to-queue handoff time (minutes) before / after AI adoption; empty if not disclosed |
| `n_misrouted`, `n_total` | **DV3** inputs | disclosed misrouted tickets and total tickets in the same period |
| `esc_thresholds`, `circuit_breaker`, `audit_logging` | **DV4** inputs | 1 if the protocol is documented, else 0 |

Derived: `dT_handoff_pct = (t_legacy_min - t_ai_min) / t_legacy_min * 100`, `r_bounce_pct = n_misrouted / n_total * 100`, `i_gov = esc_thresholds + circuit_breaker + audit_logging`.

Coding rules: two coders code DV1 independently (file `coder_agreement.csv`); disagreements are resolved by discussion; weighted kappa must be >= 0.70 (guardrail G2). MTTR/"automated routing" terms are normalised to the definitions above before coding.
