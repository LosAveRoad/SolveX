# Review — Model 1: Sub-Seasonal Survival Inversion of Latent Fan Votes

## Verification performed (evidence)

All headline numbers in `results.json` were **independently recomputed** from the deliverable
`fanvote_estimates.csv` (2,777 rows) and the shared data (`01_modeling/shared_data/`), and all
reproduce exactly:

| claim | recomputed | status |
|---|---|---|
| top-1 elimination hit of φ̂ | **0.6700** (csv: 0.6700) | ✅ match |
| top-2 replication | **0.8956** (csv: 0.8956) | ✅ match |
| AUC of simulated P(eliminated) | **0.9592** (sklearn recompute 0.9592) | ✅ match |
| Brier all / events-only | **0.0470 / 0.2901** (exact) | ✅ match |
| Kendall τ(φ̂_last, −placement) | **+0.7993** (n=411) | ✅ match |
| mean P(elim) vs event rate | **0.1088 vs 0.1085** (297/2738) | ✅ calibrated |
| σ_u (frailty sd) | **0.6458**; u ∈ [−0.892, +0.421] | ✅ match |
| corr(u, n_danced_weeks) | **−0.5891** | ✅ match |
| corr(u, judge_pct) | **+0.1130** | ✅ match |
| median 90% CI width / week-1 / week≥6 | **0.0954 / 0.0848 / 0.1135** | ✅ match |
| corr(width, 1−q_w) and corr(width, u_sd) | **−0.2448 / +0.1086** | ✅ match |
| γ = 8.0 grid (top-1 hit ≈ 0.4209–0.4175) | selected 8.0 | ✅ match |
| m₀ = 200 NLL 0.163 (vs 0.178 @800, 0.218 @10) | selected 200 | ✅ match |
| φ̂ sums to 1 in all 335 weeks; all φ̂ > 0 | min 0.999997, max 1.000002 | ✅ pass |
| Dirichlet↔Beta band overlap | **100%** of 2,738 couple-weeks | ✅ pass |
| LOSO | AUC 0.817 vs 0.824 (Δ +0.008), top-1 0.679 vs 0.670, top-2 0.892 vs 0.896 | ✅ stable |
| counts | 2,777 rows / 2738 supervision / 297 events / 39 withdrew / 34 seasons | ✅ match |
| baselines | judge-share 0.4276 (= judge-rank 0.4276), Bel-only 0.4209/0.6229, hazard-only 0.3838 (= −cumhaz 0.3838) | ✅ match |

Additionally verified: `run.py` executed twice with **bit-identical** checksums
(`fanvote_estimates.csv` 567fc95e…, `results.json` be552214…) — determinism claim confirmed.
The bottom-2 replication was also recomputed restricted to single-cut and double-cut weeks
(232/32 event weeks): 0.728 single-cut, 27/32 double-cut — consistent with the blended 0.735
over all 264 event weeks.

## Issues Found

The **computed deliverables are all correct**. The only defects found are **stale numbers in
the prose of `results_summary.md`** (they are narrative descriptions, not exported data, and do
not affect any downstream consumer):

1. "mean posterior sd ≈ 0.19" — actual mean per-couple posterior sd of the frailty is **0.588** (mean over 405 supervision couples; by status: 0.596 finalists, 0.572 eliminated). The 0.19 figure matches nothing in the data.
2. "D–S share intervals median width 0.024" — actual median D–S interval width **3.8e-05** (3.838e-05); per-season medians range 2.85e-05 (S2) to 4.30e-05 (S20).
3. "finale φ̂ 0.433" (Bristol Palin) — actual final φ̂ **0.3752**.
4. "a final φ̂ of 0.438 (finale week)" (Jerry Rice) — actual **0.3948**.
5. "Bobby Bones holds φ̂ ≈ 0.13–0.25" — actual φ̂ range **[0.131, 0.347]**.
6. "judge percentiles of 0.17–0.38" (Bobby) — actual judge_pct range **[0.1667, 0.615]**; Jerry's "0.25–0.67" matches, Bristol's "0.12–0.82" appears as [0.125, 0.818] ✅.
7. "(IQR 0.071–0.115)" for the 90% width — actual IQR **[0.0816, 0.1121]**.

These prose numbers should be refreshed before the report is circulated; no re-run is needed.

## Fix Instructions

Only textual edits to `02_programming/model_1/results_summary.md` (workflow prose) are needed:

- §Headline validation: no changes (all values reproduce).
- §Frailty line: replace "mean posterior sd ≈ 0.19" with "≈ 0.59 (σ_u = 0.646)".
- §Belief layer: replace "median width 0.024" with "≈ 3.8e-05".
- §Iconic contestants: Bobby φ̂ ≈ 0.13–0.35 vs judge pct 0.17–0.62; Jerry finale φ̂ 0.395; Bristol finale φ̂ 0.375; Joey φ̂ 0.09→0.19 (correct as is).
- §Uncertainty: replace "(IQR 0.071–0.115)" with "(IQR 0.082–0.112)".

After these edits every number in the summary is exactly backed by
`fanvote_estimates.csv` / `results.json`, which themselves were re-verified
deterministically (two consecutive `run.py` executions produce identical checksums).

## Model correctness assessment

- The cloglog GLM, EB frailty closure, truncated Dempster–Shafer combination, and
  Dirichlet pseudo-ballot uncertainty layer are implemented consistently with the master plan.
  In particular, the plan's φ̂ ∝ Bel·exp(−τu) fusion is exercised exactly (τ=1.0 pre-registered,
  0.5/1.5 reported as sensitivity in `phi.top1_hit_by_tau`), the D–S focal masses use the
  truncation constant b=4 as documented, and certainty (interval width) is correctly driven by
  the panel discount q_w and the frailty posterior sd rather than by the frame-size-dominated
  fused conflict K̃ (limitation 1 is honestly flagged and K̃ is exported audit-only).
- Validation is in-sample and honest about it (LOSO refits per season, drop ≤ 0.009), uses a
  fixed per-(season,week)-seeded Dirichlet simulation, and excludes withdrew couples from
  supervision. The elimination-reproduction target (≥60% with the ~65% theoretical max
  acknowledged) is met (0.670/0.896), and the model beats all three judge-only baselines
  (+24.3 pp top-1, +26.3 pp top-2 over judge share).
- Limitations 2–6 are appropriate disclosures, not errors; limitation 4 (Diana Nyad) is a
  genuine source-data quirk handled by the stated censoring convention.

Verdict: numerically sound and reproducible; SATISFIED after the cosmetic prose corrections listed above.

VERIFICATION_RESULT: SATISFIED
